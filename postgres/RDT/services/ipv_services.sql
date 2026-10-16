DROP TABLE IF EXISTS disruptions.ipv_services;
CREATE TABLE disruptions.ipv_services AS
WITH 
-- Normalise booleans, coalesce sort time, and keep raw times
normalised AS (
    SELECT
        "Service:RDT-ID",
        "Service:Type",
        "Stop:Station name"                                          AS from_stop,
        "Stop:Departure time"                                        AS dep_time,
        "Stop:Arrival time"                                          AS arr_time,
        COALESCE("Stop:Departure time", "Stop:Arrival time")         AS _sort_time,
        ("Stop:Departure cancelled"::text = 'true')                  AS dep_cancelled,
        ("Stop:Arrival cancelled"::text   = 'true')                  AS arr_cancelled
    FROM disruptions.services_combined
    WHERE "Service:Type" IN (
        'Bus',
        'Belbus ipv trein',
        'Metro ipv trein',
        'OV-bus ipv trein',
        'Snelbus ipv trein',
        'Stopbus ipv trein',
        'Taxibus ipv trein'
    )
),
-- Use LEAD() to get the next stop and its arrival time
legs AS (
    SELECT
        "Service:RDT-ID",
        "Service:Type",
        from_stop,
        LEAD(from_stop)     OVER w AS to_stop,
        dep_time,
        LEAD(arr_time)      OVER w AS to_arr_time,
        dep_cancelled,
        LEAD(arr_cancelled) OVER w AS to_arr_cancelled
    FROM normalised
    WINDOW w AS (PARTITION BY "Service:RDT-ID" ORDER BY _sort_time)
),
-- Drop terminal stops and compute per-leg travel time 
valid_legs AS (
    SELECT
        "Service:RDT-ID",
        "Service:Type",
        from_stop,
        to_stop,
        dep_time,                                                    -- retained for headway calc
        (dep_cancelled OR COALESCE(to_arr_cancelled, false))     AS leg_cancelled,
        (to_arr_time - dep_time)                                 AS travel_time
    FROM legs
    WHERE to_stop IS NOT NULL
      AND dep_time IS NOT NULL
      AND to_arr_time IS NOT NULL
      AND DATE(dep_time) = DATE(to_arr_time)
),
-- Compute per-departure headway on each edge
-- Only non-cancelled services are used: a cancelled trip doesn't serve passengers, so it shouldn't "reset" the headway clock.
headway_raw AS (
    SELECT
        from_stop,
        to_stop,
        dep_time - LAG(dep_time) OVER (
            PARTITION BY from_stop, to_stop, DATE(dep_time)
            ORDER BY dep_time
        )                                                        AS headway
    FROM valid_legs
    WHERE NOT leg_cancelled
),
-- Aggregate headways per edge
edge_headways AS (
    SELECT
        from_stop,
        to_stop,
        AVG(headway)                                             AS avg_headway,
        MAX(headway)                                             AS max_headway
    FROM headway_raw
    WHERE headway IS NOT NULL          -- first departure on an edge has no predecessor
      AND headway > INTERVAL '0'       -- guard against duplicate dep_times
    GROUP BY from_stop, to_stop
),
-- Count distinct services per (edge, type)
type_counts AS (
    SELECT
        from_stop,
        to_stop,
        "Service:Type",
        COUNT(DISTINCT "Service:RDT-ID") AS n_services_of_type
    FROM valid_legs
    GROUP BY from_stop, to_stop, "Service:Type"
),
-- Aggregate totals per edge, including max travel time
edge_totals AS (
    SELECT
        from_stop,
        to_stop,
        COUNT(DISTINCT "Service:RDT-ID")                                AS total_services,
        SUM(leg_cancelled::int)                                         AS cancelled_services,
        MAX(travel_time)                                                AS max_travel_time,
        PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY travel_time)        AS p90_travel_time
    FROM valid_legs
    GROUP BY from_stop, to_stop
),
-- Aggregate type arrays per edge
edge_types AS (
    SELECT
        from_stop,
        to_stop,
        ARRAY_AGG("Service:Type"      ORDER BY n_services_of_type DESC) AS service_types,
        ARRAY_AGG(n_services_of_type  ORDER BY n_services_of_type DESC) AS service_type_counts,
        jsonb_object_agg("Service:Type", n_services_of_type)            AS service_type_breakdown
    FROM type_counts
    GROUP BY from_stop, to_stop
)
-- Final select
SELECT
    e.from_stop                                                     AS departure_station,
    e.to_stop                                                       AS arrival_station,
    e.total_services,
    e.cancelled_services,
    ROUND(
        e.cancelled_services::numeric
        / NULLIF(e.total_services, 0) * 100
    , 2)                                                            AS pct_cancellations_per_total_services,
    e.max_travel_time,
    ROUND(EXTRACT(EPOCH FROM e.p90_travel_time) / 60)               AS p85_max_travel_time_minutes,
    ROUND(EXTRACT(EPOCH FROM h.avg_headway) / 60)                   AS avg_headway_minutes,
    ROUND(EXTRACT(EPOCH FROM h.max_headway) / 60)                   AS max_headway_minutes,
	CEIL(120 / ROUND(EXTRACT(EPOCH FROM h.avg_headway) / 60))		AS services_in_2hrs,com
	CEIL(120 / ROUND(EXTRACT(EPOCH FROM h.avg_headway) / 60))*50 	AS capacity, 
    t.service_types,
    t.service_type_counts,
    t.service_type_breakdown
FROM edge_totals e
JOIN edge_types t
    ON t.from_stop = e.from_stop
    AND t.to_stop  = e.to_stop
LEFT JOIN edge_headways h                -- LEFT JOIN: edges with only 1 non-cancelled
    ON h.from_stop = e.from_stop         -- service will have NULL headways
    AND h.to_stop  = e.to_stop
ORDER BY max_travel_time DESC;

-- Indexes for joins
CREATE INDEX ON disruptions.ipv_services (departure_station, arrival_station);

SELECT * FROM disruptions.ipv_services WHERE departure_station = 'Maastricht' OR arrival_station = 'Maastricht' ORDER BY departure_station ASC
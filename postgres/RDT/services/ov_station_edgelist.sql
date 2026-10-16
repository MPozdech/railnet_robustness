-- This creates an edgelist for every direct non-train connection between two stations.

DROP TABLE IF EXISTS ov_station_edgelist CASCADE;
CREATE TABLE ov_station_edgelist AS

WITH

-- Unnest route arrays into one row per (route, direction, stop_position)
route_stops_unnested AS (
    SELECT
        mr.route_id,
        mr.direction_id,
        mr.route_short_name,
        mr.route_long_name,
        mr.canonical_trip_count,
        r.agency_id,
        stop_id,
        stop_name,
        travel_time_sec,
        pos - 1 AS stop_index   -- 0-based index into the array
    FROM master_routes_ov mr
    JOIN routes r ON r.route_id = mr.route_id,
    -- Unnest parallel arrays together using WITH ORDINALITY to preserve position
    LATERAL UNNEST(mr.stop_ids, mr.stop_names, mr.travel_times_sec)
        WITH ORDINALITY AS u(stop_id, stop_name, travel_time_sec, pos)
),

-- Join each unnested stop to station_stop_groups to find which train station (if any) this stop belongs to
route_stops_with_station AS (
    SELECT
        rsu.*,
        ssg.station_id,
        ssg.station_name,
        ssg.station_code
    FROM route_stops_unnested rsu
    JOIN station_stop_groups ssg ON ssg.stop_id = rsu.stop_id
),

-- Self-join to find all pairs of station-stops on the same route+direction where source appears before target (stop_index ordering preserved from array)
station_pairs AS (
    SELECT
        src.route_id,
        src.direction_id,
        src.agency_id,
        src.route_short_name,
        src.route_long_name,
        src.station_id      AS source_station_id,
        src.station_name    AS source_station_name,
        src.station_code    AS source_station_code,
        src.stop_id         AS source_stop_id,
        src.stop_name       AS source_stop_name,
        src.stop_index      AS source_stop_index,
        tgt.station_id      AS target_station_id,
        tgt.station_name    AS target_station_name,
        tgt.station_code    AS target_station_code,
        tgt.stop_id         AS target_stop_id,
        tgt.stop_name       AS target_stop_name,
        tgt.stop_index      AS target_stop_index
    FROM route_stops_with_station src
    JOIN route_stops_with_station tgt
        ON  tgt.route_id     = src.route_id
        AND tgt.direction_id = src.direction_id
        AND tgt.stop_index   > src.stop_index
        AND tgt.station_id  != src.station_id
),

-- Sum travel_times_sec for all stops from source+1 up to and including target
-- Travel time on a stop = time to arrive AT that stop from the previous stop
travel_times AS (
    SELECT
        sp.route_id,
        sp.direction_id,
        sp.agency_id,
        sp.route_short_name,
        sp.route_long_name,
        sp.source_station_id,
        sp.source_station_name,
        sp.source_station_code,
        sp.source_stop_id,
        sp.source_stop_name,
        sp.target_station_id,
        sp.target_station_name,
        sp.target_station_code,
        sp.target_stop_id,
        sp.target_stop_name,
        SUM(rsu.travel_time_sec) AS total_travel_time_sec
    FROM station_pairs sp
    JOIN route_stops_unnested rsu
        ON  rsu.route_id     = sp.route_id
        AND rsu.direction_id = sp.direction_id
        -- Sum only the legs between source and target (exclusive of source, inclusive of target)
        AND rsu.stop_index   > sp.source_stop_index
        AND rsu.stop_index  <= sp.target_stop_index
    GROUP BY
        sp.route_id, sp.direction_id, sp.agency_id,
        sp.route_short_name, sp.route_long_name,
        sp.source_station_id, sp.source_station_name, sp.source_station_code,
        sp.source_stop_id, sp.source_stop_name,
        sp.target_station_id, sp.target_station_name, sp.target_station_code,
        sp.target_stop_id, sp.target_stop_name
)

SELECT DISTINCT ON (source_station_id, target_station_id)
    source_station_id,
    source_station_name,
    source_station_code,
    source_stop_id,
    source_stop_name,
    target_station_id,
    target_station_name,
    target_station_code,
    target_stop_id,
    target_stop_name,
    agency_id,
    route_id,
    direction_id,
    route_short_name,
    route_long_name,
    total_travel_time_sec,
    ROUND(total_travel_time_sec / 60.0, 2) AS travel_time_ov_min
FROM travel_times
WHERE lower(route_long_name) NOT LIKE '%night%' 
	AND lower(route_long_name) NOT LIKE '%nacht%'
ORDER BY source_station_id, target_station_id, total_travel_time_sec;

SELECT * FROM ov_station_edgelist;

ALTER TABLE ov_station_edgelist ADD COLUMN IF NOT EXISTS avg_peak_headway_min numeric;

WITH weekday_peak_departures AS (
    SELECT
        t.route_id,
        t.direction_id,
        st.stop_id,
        cd.date + st.departure_time AS departure_ts
    FROM stop_times st
    JOIN trips t           ON t.trip_id     = st.trip_id
    JOIN calendar_dates cd ON cd.service_id = t.service_id
                          AND cd.exception_type = 'added'
    WHERE
        st.departure_time >= '07:00:00'::interval
        AND st.departure_time <  '09:00:00'::interval
        AND EXTRACT(DOW FROM cd.date) BETWEEN 1 AND 5
),

headways AS (
    SELECT
        route_id,
        direction_id,
        stop_id,
        EXTRACT(EPOCH FROM (
            departure_ts - LAG(departure_ts) OVER (
                PARTITION BY route_id, direction_id, stop_id, departure_ts::date
                ORDER BY departure_ts
            )
        )) / 60.0 AS headway_min
    FROM weekday_peak_departures
),

avg_headways AS (
    SELECT
        route_id,
        direction_id,
        stop_id,
        ROUND(AVG(headway_min)::numeric, 1) AS avg_headway_min,
        COUNT(*) + 1                         AS num_departures
    FROM headways
    WHERE headway_min IS NOT NULL
      AND headway_min > 0
    GROUP BY route_id, direction_id, stop_id
)

UPDATE ov_station_edgelist sc
SET
    avg_peak_headway_min  = ah.avg_headway_min
FROM avg_headways ah
WHERE ah.route_id     = sc.route_id
  AND ah.direction_id = sc.direction_id
  AND ah.stop_id      = sc.source_stop_id;
  
  
SELECT * FROM ov_station_edgelist ORDER BY source_station_name ASC;
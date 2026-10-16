DROP TABLE IF EXISTS disruptions.disruption_replacement_services;
CREATE TABLE disruptions.disruption_replacement_services AS
/*
This takes the RDT service data and creates an lists the
bus replacement service that ran between 2023 and 2025.
*/

WITH
-- Keep only the replacement ("ipv trein") stops
ipv_stops AS (
    SELECT
        "Service:RDT-ID"      AS service_rdt_id,
        "Service:Type"        AS service_type,
        "Stop:Station code"   AS stop_code,
        "Stop:Arrival time"   AS arr_time,
        "Stop:Departure time" AS dep_time
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
/*
Explode each disruption into one row per impacted station code 
rdt_station_codes looks like 'GDM, HT, ZBM' (comma + space) -> trim it.
Key on rdt_id, NOT id: 'id' is not unique in disruptions_combined
(it collides across the combined per-year source tables), whereas
rdt_id is the source system's unique disruption identifier. The
disruption window is carried along here so later never has to touch
disruptions_combined again on the ambiguous id.
*/
disruption_stations AS (
    SELECT
        d.rdt_id             AS disruption_id,
        d.start_time,
        d.end_time,
        trim(code)           AS stop_code
    FROM disruptions.disruptions_combined d,
         unnest(string_to_array(d.rdt_station_codes, ',')) AS code
    WHERE trim(code) <> ''
),
/*
Match replacement stops to disruptions 
Same station code AND the stop fell inside the disruption window.
Origin stops have no arrival / terminal stops no departure, so we
accept either the arrival OR the departure time landing in the window.
DISTINCT collapses to one row per (disruption, service) even when the
service touched several impacted stations of the same disruption.
*/
matched_services AS (
    SELECT DISTINCT
        ds.disruption_id,
        s.service_rdt_id,
        s.service_type
    FROM disruption_stations ds
    JOIN ipv_stops s
        ON s.stop_code = ds.stop_code
       AND (
                s.arr_time BETWEEN ds.start_time AND ds.end_time
             OR s.dep_time BETWEEN ds.start_time AND ds.end_time
           )
),
-- Count unique services per (disruption, service type)
type_counts AS (
    SELECT
        disruption_id,
        service_type,
        COUNT(*) AS n_services          -- COUNT(*) over the DISTINCT set = unique RDT-IDs
    FROM matched_services
    GROUP BY disruption_id, service_type
),
-- Roll up to one row per disruption
disruption_agg AS (
    SELECT
        disruption_id,
        SUM(n_services)                                                  AS replacement_services,
        ARRAY_AGG(service_type ORDER BY n_services DESC)                 AS service_types,
        ARRAY_AGG(n_services   ORDER BY n_services DESC)                 AS service_type_counts,
        jsonb_object_agg(service_type, n_services)                       AS service_type_breakdown
    FROM type_counts
    GROUP BY disruption_id
)
-- Final select: every disruption, with 0 / '{}' when nothing matched
SELECT
    d.*,
    COALESCE(a.replacement_services, 0)                                 AS replacement_services,
    a.service_types,
    a.service_type_counts,
    COALESCE(a.service_type_breakdown, '{}'::jsonb)                     AS service_type_breakdown
FROM disruptions.disruptions_combined d
LEFT JOIN disruption_agg a
    ON a.disruption_id = d.rdt_id
ORDER BY replacement_services DESC;

-- Index for fast lookups back onto the disruption id
CREATE INDEX ON disruptions.disruption_replacement_services (rdt_id);

SELECT * FROM disruptions.disruption_replacement_services WHERE replacement_services = 0 ORDER BY duration_minutes DESC
DROP TABLE IF EXISTS disruptions.disrupted_services_combined;
CREATE TABLE disruptions.disrupted_services_combined AS

/*
This takes the combined historical services and counts the number of 
services that operated along a service edge and the number of services
that were cancelled along this edge across the 3 years.
*/

WITH 

-- Normalise booleans and coalesce sort time
normalised AS (
    SELECT
        "Service:RDT-ID",
        "Stop:Station name"                                         AS from_stop,
        COALESCE("Stop:Departure time", "Stop:Arrival time")        AS _sort_time,
        ("Stop:Departure cancelled"::text = 'true')                 AS dep_cancelled,
        ("Stop:Arrival cancelled"::text   = 'true')                 AS arr_cancelled
    FROM disruptions.services_combined
	WHERE 
		"Service:Type" IN (
		'Sprinter',
		'Stoptrein',
		'Intercity',
		'Sneltrein',
		'Intercity direct',
		'Eurocity',
		'Eurocity Direct',
		'ICE',
		'ICE International',
		'Eurostar'
	) 
),

-- Use LEAD() to get the next stop within each service (= shift(-1))
legs AS (
    SELECT
        "Service:RDT-ID",
        from_stop,
        LEAD(from_stop)      OVER w AS to_stop,
        dep_cancelled,
        LEAD(arr_cancelled)  OVER w AS to_arr_cancelled
    FROM normalised
    WINDOW w AS (PARTITION BY "Service:RDT-ID" ORDER BY _sort_time)
),

-- Drop terminal stops (LEAD returns NULL at end of each partition)
valid_legs AS (
    SELECT
        "Service:RDT-ID",
        from_stop,
        to_stop,
        (dep_cancelled OR COALESCE(to_arr_cancelled, false)) AS leg_cancelled
    FROM legs
    WHERE to_stop IS NOT NULL
)

-- Aggregate per directed edge
SELECT
    from_stop as departure_station,
    to_stop as arrival_station,
    COUNT(DISTINCT "Service:RDT-ID")                                AS total_services,
    SUM(leg_cancelled::int)                                         AS cancelled_services
FROM valid_legs
GROUP BY from_stop, to_stop;

-- Indexes for fast joins onto the edge list
CREATE INDEX ON disruptions.disrupted_services_combined (departure_station, arrival_station);
SELECT * FROM disruptions.disrupted_services_combined
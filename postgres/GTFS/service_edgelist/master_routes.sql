/*	The master_routes table contains details about every route operated by heavy rail passenger service in NL.
	It contains only routes for which trips were observed in the GTFS database.
	All trips were considered - no filtering for specific days. 
	GTFS data is from 29/01/26, ovAPI.nl
	Station data is from -/09/23, rijdendetreinen.nl - some of these stations were updated by me to reflect how there are IC services that stop there. 
	
	This script also creates the stop_level and ic_segments views. */

/*	This subquery itterates over all trips to connect a route_id with a stop_name on a 
	trip from this route_id. For each stop_name on a trip it stores the order in which
	this stop is visited, the time the trip departs this stop, and what the arrival time
	at the next stop is. Also initializes the sequencing used to the closest IC stations are to every stop.
	
	This is effectively a stop_times table expanded with more information. 
	1 row = 1 stopping of a trip at 1 stop. */
DROP TABLE IF EXISTS stop_level CASCADE;
CREATE TABLE stop_level AS
    SELECT
        t.route_id::integer,
		t.direction_id,
        st.trip_id::integer,
        st.stop_sequence_consec,
        s.stop_name,
        st.departure_time::interval AS departure_time,
        LEAD(st.arrival_time::interval) OVER ( 	--this looks one row ahead from current row
            PARTITION BY st.trip_id 			--I only need the next row with the relevant trip id
            ORDER BY st.stop_sequence_consec 	--I need to make sure that the stops are in order
        ) AS next_arrival_time, 				--arrival time at next stop for given trip from current (departure) stop
    	
		---IC station matching 
		d_s.ic_station, 												--does this station have IC services stopping there?
        MAX( 															--what is the largest stop_sequence_consec that is an IC within the window?
            CASE WHEN d_s.ic_station THEN st.stop_sequence_consec END 	--returns the stop_sequence_consec if it is IC station
        ) OVER (
			PARTITION BY st.trip_id 									--create window over every trip_id
			ORDER BY st.stop_sequence_consec 							--in order of service stopping there
			ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW 			--I want all prior rows and the current row
        ) AS prev_ic_seq, 												--to find what the last Ic stop was for the current (SPR) stop 

        MIN( 															--same thing but done for the next station
        	CASE WHEN d_s.ic_station THEN st.stop_sequence_consec END
        ) OVER (
			PARTITION BY st.trip_id
			ORDER BY st.stop_sequence_consec
			ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING 
        ) AS next_ic_seq												--will be null if this stop is the terminus
	FROM stop_times st
    JOIN stops s ON s.stop_id = st.stop_id
    JOIN trips t ON t.trip_id = st.trip_id
	JOIN disruptions.stations d_s ON s.stop_name = d_s.name_long 		--done to check if a station is IC
	ORDER BY route_id, direction_id, trip_id, stop_sequence_consec ASC;

/*	This extracts the IC segments between any two stations for every trip.
	1 row = 1 unique IC segment across all trips. */
DROP TABLE IF EXISTS ic_segments;
CREATE TABLE ic_segments AS
    SELECT
        sub.trip_id,					--there are multiple rows for 1 trip_id if there are multiple IC segments
        sub.prev_ic_seq,				--the value from stop_sequence_consec which is the last IC station
        sub.next_ic_seq,				--same but next station
        ARRAY_AGG(sl.stop_name ORDER BY sl.stop_sequence_consec) AS stations_between,
		MIN(sl2.stop_name) as ic_segment_start,	--these are all the same, just pull one out
		MIN(sl3.stop_name) as ic_segment_end,	--also all identical
		STRING_AGG(sl.stop_name, '=' ORDER BY sl.stop_sequence_consec) AS stations_between_str
	FROM 
		(SELECT DISTINCT 						--I want to select distinct combinations of...
			trip_id,							--trip ids,
			prev_ic_seq,						--previous ic stations, &
			next_ic_seq							--next ic stations,
		FROM stop_level		
		WHERE prev_ic_seq IS NOT NULL 			--where an IC segment was detected,
		  AND next_ic_seq IS NOT NULL			--meaning at least 1 IC station is present on this trip.
		ORDER BY trip_id ASC
		) sub
    JOIN stop_level sl									--join back to stop_level where
      	ON sl.trip_id = sub.trip_id						--on matching trip_ids and
     	AND sl.stop_sequence_consec						--stop sequence
        BETWEEN sub.prev_ic_seq AND sub.next_ic_seq 	--extract names for those stations between the two IC indicies
	JOIN stop_level sl2									--join back to stop_level but...
		ON sl2.trip_id = sub.trip_id
		AND sl2.stop_sequence_consec = sub.prev_ic_seq	--I only want the station name with the previous IC station's index
	JOIN stop_level sl3									--join back to stop_level but...
		ON sl3.trip_id = sub.trip_id
		AND sl3.stop_sequence_consec = sub.next_ic_seq	--I only want the station name with the next IC station's index
    GROUP BY 					--this creates group of unique combinations of the stations_between arrays 
        sub.trip_id, 			--the aggregation happens over a specific trip id,
        sub.prev_ic_seq, 		--then across a trip's previous ic station
        sub.next_ic_seq 		--and its next IC station
	ORDER BY trip_id ASC; 		--this is just to check if the calc is consistent

DROP TABLE IF EXISTS master_routes CASCADE;
CREATE TABLE master_routes AS

/*	This for every trip aggregates its stops into an array.
	1 row = 1 trip */
WITH trip_patterns AS (
    SELECT
        sl.trip_id,
		sl.route_id,
		sl.direction_id,
        ARRAY_AGG(sl.stop_name ORDER BY sl.stop_sequence_consec) AS stops, 								--aggregation order must be in the stop sequence
		string_agg(sl.stop_name, ',' ORDER BY sl.stop_sequence_consec) AS stops_str, 					--makes it easier to check if some string is contained
		ARRAY_AGG(sl.ic_station::integer ORDER BY sl.stop_sequence_consec) AS ic_stations,				--stores what stations are IC along a stop-pattern
		ARRAY_AGG(ics.stations_between_str ORDER BY sl.stop_sequence_consec) AS stations_string_agg, 	--debug array where 1 value = the IC segment this stop is connected to
		
		ARRAY_AGG(ics.ic_segment_start ORDER BY sl.stop_sequence_consec) AS ic_segment_starts,
		ARRAY_AGG(ics.ic_segment_end ORDER BY sl.stop_sequence_consec) AS ic_segment_ends
    FROM stop_level sl
	LEFT JOIN ic_segments ics 
		ON ics.trip_id = sl.trip_id
		AND ics.prev_ic_seq = sl.prev_ic_seq
		AND ics.next_ic_seq = sl.next_ic_seq
    GROUP BY 
		sl.trip_id, --aggregates many-trips-to-many-stops to 1-trip-1-stopArray
		sl.route_id,
		sl.direction_id
	ORDER BY sl.trip_id ASC
),

/*	This groups trips by every unique pattern of stops observed per route-direction. 
	1 row = 1 unique pattern of stops per route-direction. */
pattern_counts AS (
    SELECT
        sl.route_id,
		sl.direction_id,
        stops,
        COUNT(*) AS observation_count,						--count total number of trips for this route-direction
		COUNT(*) OVER (
				PARTITION BY sl.route_id, sl.direction_id 	--count how many different patterns were observed
			) AS unique_pattern_count
    FROM trip_patterns tp
	JOIN stop_level sl 
		ON sl.trip_id = tp.trip_id
    GROUP BY sl.route_id, sl.direction_id, stops
	ORDER BY sl.route_id, sl.direction_id ASC
),

/*	This table expands the routes table.
	Extracts the intended termini from the route_long_name.
	Assigns directions based on direction. 
	1 row = 1 route-direction */
routes_per_direction AS (
	SELECT
		r.route_id::integer,
		v.direction,
		v.terminus,
		REGEXP_REPLACE(r.route_long_name, '^(.+?) <-> .+$', '\1') as start_station,
		REGEXP_REPLACE(r.route_long_name, '^.*? <-> (.*?)(?:\s+[A-Z0-9]+)?$', '\1') as end_station
	FROM routes r
	CROSS JOIN LATERAL (		--I want to expand the table for every route_long_name by the direction and terminus
		VALUES
			(1, REGEXP_REPLACE(r.route_long_name, '^(.+?) <-> .+$', '\1')),
			(0,   REGEXP_REPLACE(r.route_long_name, '^.*? <-> (.*?)(?:\s+[A-Z0-9]+)?$', '\1'))
	) v(direction, terminus)	--a terminus is the intended end_station of a line. 
	WHERE 
		r.route_type = '2'		--I only care about heavy passenger rail
		AND r.route_short_name ~ '(Stoptrein|Sneltrein|Intercity|Intercity direct|Sprinter)' --I don't want international (ICE) trains
		AND r.route_long_name NOT LIKE 'Nachtnettrein%'		--also out of scope, incorrectly classifed
	ORDER BY route_id, direction ASC
),

/*	This checks if every unique stop pattern started and ended at the intended stations. 
	1 row = 1 unique combination of stop patterns per route-direction. */
pattern_with_terminals AS (
    SELECT
		pc.route_id,
		pc.direction_id,
		pc.stops,
        (
            pc.stops[1] = CASE 									--select first stop in route pattern
                WHEN rpd.direction = 0 THEN rpd.start_station 	--what station is first depends on direction
                ELSE rpd.end_station 							--return the name of station that is the first
            END
            AND pc.stops[array_length(pc.stops,1)] = CASE
                WHEN rpd.direction = 0 THEN rpd.end_station
                ELSE rpd.start_station
            END
        ) AS matches_terminals
    FROM pattern_counts pc
    JOIN routes_per_direction rpd 					--this extracts the intended start and end (terminal) stops of every route 
		ON rpd.route_id = pc.route_id
		AND rpd.direction = pc.direction_id
	ORDER BY pc.route_id, pc.direction_id ASC
),

/*	This ranks each of the unique stop-patterns from pattern_counts
	where it first checks if the termini are matching and
	then which pattern had the most observations. */
ranked_patterns AS (
	SELECT
		pc.route_id,
		pc.direction_id,
		pc.stops,
        ROW_NUMBER() OVER ( 				--for each pattern ranks it grouped by...
            PARTITION BY pc.route_id, pc.direction_id
            ORDER BY
                matches_terminals DESC,     --first ranks matching patterns
                observation_count DESC      --then ranks observations
        ) AS rn								--where 1 is the most-representative stop-order based on prior 2 conditions. 
    FROM pattern_with_terminals pwt
	JOIN routes_per_direction rpd
		ON rpd.route_id = pwt.route_id
		AND rpd.direction = pwt.direction_id
	JOIN pattern_counts pc
		ON pc.route_id = pwt.route_id
		AND pc.direction_id = pwt.direction_id
		AND pc.stops = pwt.stops
	ORDER BY pc.route_id, pc.direction_id ASC
),

total_trip_counts AS (
    SELECT
        sl.route_id,
        sl.direction_id,
        COUNT(*) AS total_trip_count
    FROM trip_patterns tp
	JOIN stop_level sl
		ON sl.trip_id = tp.trip_id
    GROUP BY sl.route_id, sl.direction_id
),

/*	This collects everything until now into a table where
	1 row = 1 route-direction. */
representative_routes AS (
	SELECT
		rp.route_id,
		rp.direction_id,
		rp.stops,
		pwt.matches_terminals,
		pc.observation_count,
		ttc.total_trip_count,
		pc.unique_pattern_count,
		MIN(tp.trip_id) AS representative_trip_id,	--I just need 1 trip_id that corresponds to the group
		
		tp.ic_segment_starts,
		tp.ic_segment_ends,
		tp.stations_string_agg
	FROM ranked_patterns rp
	JOIN pattern_with_terminals pwt
		ON pwt.route_id = rp.route_id
		AND pwt.direction_id = rp.direction_id
		AND pwt.stops = rp.stops
	JOIN pattern_counts pc
		ON pc.route_id = rp.route_id
		AND pc.direction_id = rp.direction_id
		AND pc.stops = rp.stops
	JOIN trip_patterns tp
		ON tp.stops = rp.stops
		AND tp.route_id = rp.route_id
		AND tp.direction_id = rp.direction_id
	JOIN total_trip_counts ttc
		ON ttc.route_id = rp.route_id
		AND ttc.direction_id = rp.direction_id
	WHERE rp.rn=1	--only return the highest ranking stop-pattern per rotue-direction
	GROUP BY
		rp.route_id,
		rp.direction_id,
		rp.stops,
		pwt.matches_terminals,
		pc.observation_count,
		ttc.total_trip_count,
		pc.unique_pattern_count,
		tp.ic_segment_starts,
		tp.ic_segment_ends,
		tp.stations_string_agg	--maybe  a MIN() call could be used here instead of grouping?
	ORDER BY rp.route_id ASC 
),

travel_times AS (
	SELECT 
		rr.representative_trip_id,
		ARRAY_AGG(
            sl.next_arrival_time - sl.departure_time
            ORDER BY sl.stop_sequence_consec
        ) AS travel_times
	FROM representative_routes rr
	JOIN stop_level sl
		ON sl.trip_id = rr.representative_trip_id
		AND sl.route_id = rr.route_id
		AND sl.direction_id = rr.direction_id
	WHERE sl.next_arrival_time IS NOT NULL
	GROUP BY
		rr.representative_trip_id
)

SELECT
	rr.route_id,		--pk
	rr.direction_id,	--pk
	r.agency_id,
	rr.representative_trip_id,
	r.route_short_name,
	r.route_long_name,
	rpd.start_station,
	rpd.end_station,
	rpd.terminus,
	rr.stops,
	rr.matches_terminals,
	CARDINALITY(rr.stops) AS stop_count,
	tt.travel_times,
	pc.observation_count,
	ttc.total_trip_count,
	round(pc.observation_count::numeric / ttc.total_trip_count * 100, 2) AS pattern_share,
	pc.unique_pattern_count,
	rr.ic_segment_starts,
	rr.ic_segment_ends,
	rr.stations_string_agg
FROM representative_routes rr
JOIN routes r
	ON r.route_id::integer = rr.route_id
JOIN routes_per_direction rpd
	ON rpd.route_id = rr.route_id
	AND rpd.direction = rr.direction_id
JOIN travel_times tt
	ON tt.representative_trip_id = rr.representative_trip_id
JOIN pattern_counts pc
	ON pc.route_id = rr.route_id
	AND pc.direction_id = rr.direction_id
	AND pc.stops = rr.stops
JOIN total_trip_counts ttc
	ON ttc.route_id = rr.route_id
	AND ttc.direction_id = rr.direction_id
ORDER BY rr.route_id, rr.direction_id ASC;
SELECT * FROM master_routes;
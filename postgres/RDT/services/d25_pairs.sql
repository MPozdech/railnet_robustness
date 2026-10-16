/*	This query calculates some extra stats on the raw disruption dataset,
	then binds it to the node_pairs from GTFS assuming any mention of a station in RDT
	means it disrupted BOTH directions between these two stations. 
	GTFS is the ground truth for station order. */

DROP TABLE IF EXISTS disruptions.d25_pairs; 
CREATE TABLE disruptions.d25_pairs AS
/*	First the raw table file is to extract the disrupted stations into an array and add any extra info. 
	This is for an unfiltered table, but could add only for some weekday or time, or exclude some
	disruption causes like strikes. */
WITH d_adj AS(
	SELECT 
		id, rdt_id, ns_lines, rdt_lines, rdt_lines_id, rdt_station_names,
		string_to_array(rdt_station_names, ',')::text[] as station_array,
		rdt_station_codes,
		string_to_array(rdt_station_codes, ',')::text[] as code_array,
		cause_nl, cause_en, statistical_cause_nl, statistical_cause_en, cause_group, start_time, end_time, duration_minutes,
		TO_CHAR(start_time, 'Day') as start_day, 
		TO_CHAR(end_time, 'Day') as end_day,
		(CASE 
			WHEN start_time::time BETWEEN '07:00:00' AND  '09:00:00' THEN 'morning peak'
			WHEN start_time::time BETWEEN '09:00:00' AND  '16:00:00' THEN 'midday offpeak'
			WHEN start_time::time BETWEEN '16:00:00' AND  '18:00:00' THEN 'evening peak'
			ELSE 'offpeak' END) as timeslot
	FROM disruptions.disruptions_combined --this is the table directly from the RDT csv dump
	ORDER BY start_time ASC
),

ic_segments AS(
	SELECT 
		ic_segment_start, 
		ic_segment_end, 
		stations_between
	FROM ic_segments
	GROUP BY ic_segment_start, ic_segment_end, stations_between
),

/*	This binds every disruption to a node-pair that is CONTAINED within the stations column, 
	meanign both stations must be present in the disruption station list to be connected. */
node_pairs AS(
	SELECT
		np.from_stop,
		np.to_stop,
		round(EXTRACT(EPOCH FROM np.travel_time) / 60, 0) AS travel_time,
		np.unique_agencies,
		d.*
	FROM node_pairs np
	FULL JOIN ic_segments ics
		ON ics.ic_segment_start = np.from_stop
		AND ics.ic_segment_end = np.to_stop
	JOIN d_adj d --in theory duplicating this following join for every disruption table could be scaled up very easily. Would create a big table and 'like' not very efficient.
		ON 
			(np.from_stop = ANY(d.station_array)			--the RDT stations list must contain the start
			 AND np.to_stop = ANY(d.station_array)) 		--and end stops of this specific node-pair
		OR
			(cardinality(									--what is the dimension of the array...
				ARRAY(										
					SELECT s								--when selecting matching stops
					FROM unnest(d.station_array) s			--from the disruption station array
					WHERE s = ANY(ics.stations_between)		--and the ic_segment array
				)
			) >= 2)											--if atleast 2, then this segment can be joined
	ORDER BY from_stop ASC
),


/*	This aggregates causes per node-pair and counts them. */
cause_counts AS (
    SELECT
        from_stop,
        to_stop,
        statistical_cause_en,
        COUNT(*) AS cause_count
    FROM node_pairs
    GROUP BY
        from_stop,
        to_stop,
        statistical_cause_en
),

/*	This creates arrays for each node-pair with the observed disruptions causes and their frequency. */
cause_arrays AS (
    SELECT
        from_stop,
        to_stop,
        ARRAY_AGG(statistical_cause_en ORDER BY cause_count DESC) AS causes_ordered,
        ARRAY_AGG(cause_count ORDER BY cause_count DESC) AS cause_counts
    FROM cause_counts
    GROUP BY
        from_stop,
        to_stop
),

/*	This creates a table for each pair with what the longest disruption was and why it happened. */
longest_cause AS (
    SELECT DISTINCT ON (from_stop, to_stop)
        from_stop,
        to_stop,
        statistical_cause_en AS longest_duration_cause,
        duration_minutes     AS longest_duration_minutes
    FROM node_pairs
    ORDER BY
        from_stop,
        to_stop,
        duration_minutes DESC
)

/*	The final select query that computes statistics for each node-pair. */
SELECT
    np.from_stop,
    np.to_stop,
	s1.code as from_code,
	s2.code as to_code,
	MAX(np.travel_time) as travel_time,
	np.unique_agencies,

    COUNT(*) AS disruption_count, 													--how many disruptions were observed on this pair?
    round(AVG(duration_minutes),0) AS avg_disruption_duration, 						--how long did a disruption take on average?
	MODE() WITHIN GROUP (ORDER BY np.statistical_cause_en) AS most_common_cause, 	--what was the most common disruption cause?
	min(duration_minutes) AS min_duration, 
	max(duration_minutes) AS max_duration,
	lc.longest_duration_cause AS max_duration_cause, 								--what caused the longest disruption?
	(s1.ic_station AND s2.ic_station) AS ic_segment,

	-- Counts for how many disruptions happened at different timeslots. 
	COUNT(CASE WHEN timeslot = 'morning peak' THEN np.id END) as count_morning_peak,
	COUNT(CASE WHEN timeslot = 'midday offpeak' THEN np.id END) as count_midday_offpeak,
	COUNT(CASE WHEN timeslot = 'evening peak' THEN np.id END) as count_evening_peak,
	COUNT(CASE WHEN timeslot = 'offpeak' THEN np.id END) as count_offpeak,
	
    ca.causes_ordered, 																--array with the causes in order from most to least-observed per node-pair
    ca.cause_counts, 																--how frequently each cause was observed for each pair
	ARRAY_AGG(np.statistical_cause_en) AS causes_array, 							--raw dump of all causes observed
	ARRAY_AGG(np.rdt_id) AS rdt_id_array
	
FROM node_pairs np
JOIN cause_arrays ca
  	ON ca.from_stop = np.from_stop
 	AND ca.to_stop = np.to_stop
JOIN longest_cause lc
	ON lc.from_stop = np.from_stop
	AND lc.to_stop   = np.to_stop
JOIN disruptions.stations s1
	ON s1.name_long = np.from_stop
JOIN disruptions.stations s2
	ON s2.name_long = np.to_stop
GROUP BY 
	np.from_stop, 
	np.to_stop,
	from_code,
	to_code,
	np.unique_agencies,
	ca.causes_ordered, 
	ca.cause_counts,
	lc.longest_duration_cause,
	s1.ic_station,
	s2.ic_station
ORDER BY from_stop ASC;
SELECT * from disruptions.d25_pairs;
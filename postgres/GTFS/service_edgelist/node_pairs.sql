DROP VIEW IF EXISTS node_pairs; 
CREATE OR REPLACE VIEW node_pairs AS
/*	This script takes the master_routes tables and extracts from each route the pairings 
	between two subsequent stops and aggregates the route data into arrays for each pair.
	Also contains the IC stations on whose segment a node-pair lies. 
	1 row = 1 directed pairing between two stations. */
SELECT
    from_stop,	--PK
    to_stop,	--PK


	MAX(travel_time) AS travel_time,	--this is 85% of the time the same across all, but at worst can be 3 minutes more per route. Select max to be safe. 
	COUNT(route_id) AS route_count,
	ARRAY_REMOVE(ARRAY_AGG(DISTINCT ic_segment_start), NULL) AS ic_segment_start,	--what are (all) IC stations this node-pair belongs to?
	ARRAY_REMOVE(ARRAY_AGG(DISTINCT ic_segment_end), NULL) AS ic_segment_end,
	
	--information about the routes on this node-pair
    ARRAY_AGG(route_id ORDER BY route_id, direction_id) AS route_ids,
    ARRAY_AGG(agency_id ORDER BY route_id, direction_id) AS agency_ids,
	ARRAY_AGG(DISTINCT agency_id) AS unique_agencies,
    ARRAY_AGG(route_short_name ORDER BY route_id, direction_id) AS route_short_names,
    ARRAY_AGG(route_long_name ORDER BY route_id, direction_id) AS route_long_names,
    ARRAY_AGG(direction_id ORDER BY route_id, direction_id) AS directions

FROM ( 			--this subquery does the node-pair extraction
    SELECT
        t.route_id,
        t.agency_id,
        t.route_short_name,
        t.route_long_name,
        t.direction_id,

        a.elem 	AS from_stop,
        b.elem 	AS to_stop,
        a.tt   	AS travel_time,
		a.ic_s	AS ic_segment_start,
		b.ic_e 	AS ic_segment_end
    FROM master_routes t
    CROSS JOIN LATERAL unnest(
			t.stops, 				--all of these arrays are added to the unnest
			t.travel_times,
			t.ic_segment_starts
		) 
        WITH ORDINALITY AS a(elem, tt, ic_s, idx)
    JOIN LATERAL unnest(t.stops, t.ic_segment_ends)
        WITH ORDINALITY AS b(elem, ic_e, idx)
        ON b.idx = a.idx + 1
) s
GROUP BY
    from_stop,
    to_stop
ORDER BY
    from_stop,
    to_stop;
SELECT * FROM node_pairs;
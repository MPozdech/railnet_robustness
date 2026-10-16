/*
This script takes the PC4 level CBS population polygons
and calculates the number of people living within the clipped
area found in the clipped_pc4_population shapefile (see Data folder).
*/

ALTER TABLE demand.cbs_pc4 
ADD COLUMN pc_area numeric;

UPDATE demand.cbs_pc4
SET pc_area = ST_Area(geom); -- Area of the entire PC4 level postcode

ALTER TABLE demand.clipped_pc4_population
ADD COLUMN clip_area numeric;

UPDATE demand.clipped_pc4_population
SET clip_area = ST_Area(geom); -- Area of the clipped polygon

SELECT 
	id, 
	code, 
	name_long, 
	ic_station,
	round(c.aantal_inw * (clip_area/pc_area), 0) AS population_in_clip,
	c.aantal_inw AS pop_in_clipped_poly, --total population in entire PC4
	pc_area, 	--the area of the PC4 polygon
	clip_area, 	--the area of clipped PC4 polygons
	clip_area/pc_area AS clip_area_over_pc4_area --ratio to calculate population within clip
FROM demand.clipped_pc4_population c
JOIN demand.cbs_pc4 p
ON c.postcode = p.postcode;

-- Create table with the population catchment of a station.
CREATE TABLE demand.catchments AS 
SELECT 
	code, 
	name_long, 
	sum(round(c.aantal_inw * (clip_area/pc_area), 0)) AS station_catchment
FROM demand.clipped_pc4_population c
JOIN demand.cbs_pc4 p
ON c.postcode = p.postcode
WHERE country = 'NL'
GROUP BY code, name_long
ORDER BY name_long ASC;

SELECT * FROM demand.catchments;
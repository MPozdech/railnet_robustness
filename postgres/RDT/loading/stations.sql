-- Table: disruptions.stations

-- DROP TABLE IF EXISTS disruptions.stations;

CREATE TABLE IF NOT EXISTS disruptions.stations
(
    id integer,
    code character varying COLLATE pg_catalog."default",
    uic integer,
    name_short character varying COLLATE pg_catalog."default",
    name_medium character varying COLLATE pg_catalog."default",
    name_long character varying COLLATE pg_catalog."default",
    slug character varying COLLATE pg_catalog."default",
    country character varying COLLATE pg_catalog."default",
    type_station character varying COLLATE pg_catalog."default",
    geo_lat numeric,
    geo_lng numeric,
    ic_station boolean,
    geom geometry(Point,4326)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS disruptions.stations
    OWNER to postgres;
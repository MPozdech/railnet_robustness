-- Table: public.stops

-- DROP TABLE IF EXISTS public.stops;

CREATE TABLE IF NOT EXISTS public.stops
(
    stop_id text COLLATE pg_catalog."default" NOT NULL,
    stop_code text COLLATE pg_catalog."default",
    stop_name text COLLATE pg_catalog."default",
    stop_desc text COLLATE pg_catalog."default",
    stop_loc geography(Point,4326),
    zone_id text COLLATE pg_catalog."default",
    stop_url text COLLATE pg_catalog."default",
    location_type location_type_val,
    parent_station text COLLATE pg_catalog."default",
    stop_timezone text COLLATE pg_catalog."default",
    wheelchair_boarding wheelchair_boarding_val,
    level_id text COLLATE pg_catalog."default",
    platform_code text COLLATE pg_catalog."default",
    longitude numeric,
    latitude numeric,
    CONSTRAINT stops_pkey PRIMARY KEY (stop_id),
    CONSTRAINT stops_parent_station_fkey FOREIGN KEY (parent_station)
        REFERENCES public.stops (stop_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT stops_stop_timezone_check CHECK (is_timezone(stop_timezone))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.stops
    OWNER to postgres;
-- Index: stops_parent_station_idx

-- DROP INDEX IF EXISTS public.stops_parent_station_idx;

CREATE INDEX IF NOT EXISTS stops_parent_station_idx
    ON public.stops USING btree
    (parent_station COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
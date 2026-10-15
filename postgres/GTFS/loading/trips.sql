-- Table: public.trips

-- DROP TABLE IF EXISTS public.trips;

CREATE TABLE IF NOT EXISTS public.trips
(
    trip_id text COLLATE pg_catalog."default" NOT NULL,
    route_id text COLLATE pg_catalog."default" NOT NULL,
    service_id text COLLATE pg_catalog."default" NOT NULL,
    trip_headsign text COLLATE pg_catalog."default",
    trip_short_name text COLLATE pg_catalog."default",
    direction_id integer,
    block_id text COLLATE pg_catalog."default",
    shape_id text COLLATE pg_catalog."default",
    wheelchair_accessible wheelchair_accessibility,
    bikes_allowed bikes_allowance,
    CONSTRAINT trips_pkey PRIMARY KEY (trip_id),
    CONSTRAINT trips_route_id_fkey FOREIGN KEY (route_id)
        REFERENCES public.routes (route_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.trips
    OWNER to postgres;

COMMENT ON TABLE public.trips
    IS 'Stores trip_id, route_id, shape_id';
-- Index: trips_route_id_idx

-- DROP INDEX IF EXISTS public.trips_route_id_idx;

CREATE INDEX IF NOT EXISTS trips_route_id_idx
    ON public.trips USING btree
    (route_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
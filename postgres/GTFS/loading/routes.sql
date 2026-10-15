-- Table: public.routes

-- DROP TABLE IF EXISTS public.routes;

CREATE TABLE IF NOT EXISTS public.routes
(
    route_id text COLLATE pg_catalog."default" NOT NULL,
    agency_id text COLLATE pg_catalog."default",
    route_short_name text COLLATE pg_catalog."default",
    route_long_name text COLLATE pg_catalog."default",
    route_desc text COLLATE pg_catalog."default",
    route_type route_type_val NOT NULL,
    route_url text COLLATE pg_catalog."default",
    route_color text COLLATE pg_catalog."default",
    route_text_color text COLLATE pg_catalog."default",
    route_sort_order integer,
    CONSTRAINT routes_pkey PRIMARY KEY (route_id),
    CONSTRAINT routes_agency_id_fkey FOREIGN KEY (agency_id)
        REFERENCES public.agency (agency_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.routes
    OWNER to postgres;
-- Index: routes_route_short_name_idx

-- DROP INDEX IF EXISTS public.routes_route_short_name_idx;

CREATE INDEX IF NOT EXISTS routes_route_short_name_idx
    ON public.routes USING btree
    (route_short_name COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
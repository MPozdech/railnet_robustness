-- Table: public.agency

-- DROP TABLE IF EXISTS public.agency;

CREATE TABLE IF NOT EXISTS public.agency
(
    agency_id text COLLATE pg_catalog."default" NOT NULL,
    agency_name text COLLATE pg_catalog."default" NOT NULL,
    agency_url text COLLATE pg_catalog."default" NOT NULL,
    agency_timezone text COLLATE pg_catalog."default" NOT NULL,
    agency_lang text COLLATE pg_catalog."default",
    agency_phone text COLLATE pg_catalog."default",
    agency_fare_url text COLLATE pg_catalog."default",
    agency_email text COLLATE pg_catalog."default",
    CONSTRAINT agency_pkey PRIMARY KEY (agency_id),
    CONSTRAINT valid_timezone CHECK (is_timezone(agency_timezone))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.agency
    OWNER to postgres;
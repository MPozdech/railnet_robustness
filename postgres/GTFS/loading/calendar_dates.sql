-- Table: public.calendar_dates

-- DROP TABLE IF EXISTS public.calendar_dates;

CREATE TABLE IF NOT EXISTS public.calendar_dates
(
    service_id text COLLATE pg_catalog."default" NOT NULL,
    date date NOT NULL,
    exception_type exception_type_v NOT NULL,
    CONSTRAINT calendar_dates_pkey PRIMARY KEY (service_id, date)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.calendar_dates
    OWNER to postgres;
-- Index: calendar_dates_exception_type_idx

-- DROP INDEX IF EXISTS public.calendar_dates_exception_type_idx;

CREATE INDEX IF NOT EXISTS calendar_dates_exception_type_idx
    ON public.calendar_dates USING btree
    (exception_type ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: calendar_dates_service_id_idx

-- DROP INDEX IF EXISTS public.calendar_dates_service_id_idx;

CREATE INDEX IF NOT EXISTS calendar_dates_service_id_idx
    ON public.calendar_dates USING btree
    (service_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
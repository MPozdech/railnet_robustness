-- Table: public.calendar

-- DROP TABLE IF EXISTS public.calendar;

CREATE TABLE IF NOT EXISTS public.calendar
(
    service_id text COLLATE pg_catalog."default" NOT NULL,
    monday availability NOT NULL,
    tuesday availability NOT NULL,
    wednesday availability NOT NULL,
    thursday availability NOT NULL,
    friday availability NOT NULL,
    saturday availability NOT NULL,
    sunday availability NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    CONSTRAINT calendar_pkey PRIMARY KEY (service_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.calendar
    OWNER to postgres;
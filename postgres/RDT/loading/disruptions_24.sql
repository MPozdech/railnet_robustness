-- Table: disruptions.disruptions_24

-- DROP TABLE IF EXISTS disruptions.disruptions_24;

CREATE TABLE IF NOT EXISTS disruptions.disruptions_24
(
    id integer NOT NULL DEFAULT 'nextval('disruptions.disruptions_24_id_seq'::regclass)',
    rdt_id integer,
    ns_lines character varying COLLATE pg_catalog."default",
    rdt_lines character varying COLLATE pg_catalog."default",
    rdt_lines_id character varying COLLATE pg_catalog."default",
    rdt_station_names character varying COLLATE pg_catalog."default",
    rdt_station_codes character varying COLLATE pg_catalog."default",
    cause_nl character varying COLLATE pg_catalog."default",
    cause_en character varying COLLATE pg_catalog."default",
    statistical_cause_nl character varying COLLATE pg_catalog."default",
    statistical_cause_en character varying COLLATE pg_catalog."default",
    cause_group character varying COLLATE pg_catalog."default",
    start_time timestamp without time zone,
    end_time timestamp without time zone,
    duration_minutes integer
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS disruptions.disruptions_24
    OWNER to postgres;
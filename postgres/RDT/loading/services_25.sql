-- Table: disruptions.services_25

-- DROP TABLE IF EXISTS disruptions.services_25;

CREATE TABLE IF NOT EXISTS disruptions.services_25
(
    id integer NOT NULL DEFAULT 'nextval('disruptions.services_25_id_seq'::regclass)',
    "Service:RDT-ID" integer,
    "Service:Date" date,
    "Service:Type" character varying COLLATE pg_catalog."default",
    "Service:Company" character varying COLLATE pg_catalog."default",
    "Service:Train number" integer,
    "Service:Completely cancelled" boolean,
    "Service:Partly cancelled" boolean,
    "Service:Maximum delay" integer,
    "Stop:RDT-ID" integer,
    "Stop:Station code" character varying COLLATE pg_catalog."default",
    "Stop:Station name" character varying COLLATE pg_catalog."default",
    "Stop:Arrival time" timestamp without time zone,
    "Stop:Arrival delay" integer,
    "Stop:Arrival cancelled" boolean,
    "Stop:Departure time" timestamp without time zone,
    "Stop:Departure delay" integer,
    "Stop:Departure cancelled" boolean,
    "Stop:Platform change" boolean,
    "Stop:Planned platform" character varying COLLATE pg_catalog."default",
    "Stop:Actual platform" character varying COLLATE pg_catalog."default"
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS disruptions.services_25
    OWNER to postgres;
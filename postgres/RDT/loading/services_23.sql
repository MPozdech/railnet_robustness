-- Table: disruptions.services_23

-- DROP TABLE IF EXISTS disruptions.services_23;

CREATE TABLE IF NOT EXISTS disruptions.services_23
(
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
    "Stop:Actual platform" character varying COLLATE pg_catalog."default",
    id bigint NOT NULL GENERATED ALWAYS AS IDENTITY ( INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 )
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS disruptions.services_23
    OWNER to postgres;
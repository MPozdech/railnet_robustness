-- Table: public.stop_times

-- DROP TABLE IF EXISTS public.stop_times;

CREATE TABLE IF NOT EXISTS public.stop_times
(
    trip_id text COLLATE pg_catalog."default" NOT NULL,
    arrival_time interval,
    departure_time interval,
    stop_id text COLLATE pg_catalog."default" NOT NULL,
    stop_sequence integer NOT NULL,
    stop_sequence_consec integer,
    stop_headsign text COLLATE pg_catalog."default",
    pickup_type pickup_drop_off_type,
    drop_off_type pickup_drop_off_type,
    shape_dist_traveled real,
    timepoint timepoint_v,
    trip_start_time interval,
    CONSTRAINT stop_times_stop_id_fkey FOREIGN KEY (stop_id)
        REFERENCES public.stops (stop_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT stop_times_trip_id_fkey FOREIGN KEY (trip_id)
        REFERENCES public.trips (trip_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.stop_times
    OWNER to postgres;
-- Index: stop_times_arrival_time_idx

-- DROP INDEX IF EXISTS public.stop_times_arrival_time_idx;

CREATE INDEX IF NOT EXISTS stop_times_arrival_time_idx
    ON public.stop_times USING btree
    (arrival_time DESC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_arrival_time_idx1

-- DROP INDEX IF EXISTS public.stop_times_arrival_time_idx1;

CREATE INDEX IF NOT EXISTS stop_times_arrival_time_idx1
    ON public.stop_times USING btree
    (arrival_time ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_departure_time_idx

-- DROP INDEX IF EXISTS public.stop_times_departure_time_idx;

CREATE INDEX IF NOT EXISTS stop_times_departure_time_idx
    ON public.stop_times USING btree
    (departure_time DESC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_departure_time_idx1

-- DROP INDEX IF EXISTS public.stop_times_departure_time_idx1;

CREATE INDEX IF NOT EXISTS stop_times_departure_time_idx1
    ON public.stop_times USING btree
    (departure_time ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_stop_id_idx

-- DROP INDEX IF EXISTS public.stop_times_stop_id_idx;

CREATE INDEX IF NOT EXISTS stop_times_stop_id_idx
    ON public.stop_times USING btree
    (stop_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_stop_sequence_consec_idx

-- DROP INDEX IF EXISTS public.stop_times_stop_sequence_consec_idx;

CREATE INDEX IF NOT EXISTS stop_times_stop_sequence_consec_idx
    ON public.stop_times USING btree
    (stop_sequence_consec ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_trip_id_idx

-- DROP INDEX IF EXISTS public.stop_times_trip_id_idx;

CREATE INDEX IF NOT EXISTS stop_times_trip_id_idx
    ON public.stop_times USING btree
    (trip_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: stop_times_trip_id_stop_sequence_consec_idx

-- DROP INDEX IF EXISTS public.stop_times_trip_id_stop_sequence_consec_idx;

CREATE INDEX IF NOT EXISTS stop_times_trip_id_stop_sequence_consec_idx
    ON public.stop_times USING btree
    (trip_id COLLATE pg_catalog."default" ASC NULLS LAST, stop_sequence_consec ASC NULLS LAST)
    TABLESPACE pg_default;
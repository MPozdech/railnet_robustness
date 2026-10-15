-- Table: public.shapes

-- DROP TABLE IF EXISTS public.shapes;

CREATE TABLE IF NOT EXISTS public.shapes
(
    id integer NOT NULL DEFAULT 'nextval('shapes_id_seq'::regclass)',
    shape_id text COLLATE pg_catalog."default",
    shape_pt_sequence integer,
    shape_pt_loc geography(Point,4326),
    shape_dist_traveled real,
    longitude numeric,
    latitude numeric,
    CONSTRAINT shapes_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.shapes
    OWNER to postgres;
-- Index: shapes_by_shape_id

-- DROP INDEX IF EXISTS public.shapes_by_shape_id;

CREATE INDEX IF NOT EXISTS shapes_by_shape_id
    ON public.shapes USING btree
    (shape_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
-- Index: shapes_shape_id_shape_pt_sequence_idx

-- DROP INDEX IF EXISTS public.shapes_shape_id_shape_pt_sequence_idx;

CREATE INDEX IF NOT EXISTS shapes_shape_id_shape_pt_sequence_idx
    ON public.shapes USING btree
    (shape_id COLLATE pg_catalog."default" ASC NULLS LAST, shape_pt_sequence ASC NULLS LAST)
    TABLESPACE pg_default;
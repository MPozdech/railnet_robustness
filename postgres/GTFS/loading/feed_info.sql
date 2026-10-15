-- Table: public.feed_info

-- DROP TABLE IF EXISTS public.feed_info;

CREATE TABLE IF NOT EXISTS public.feed_info
(
    feed_publisher_name text COLLATE pg_catalog."default" NOT NULL,
    feed_publisher_url text COLLATE pg_catalog."default" NOT NULL,
    feed_lang text COLLATE pg_catalog."default" NOT NULL,
    default_lang text COLLATE pg_catalog."default",
    feed_start_date date,
    feed_end_date date,
    feed_version text COLLATE pg_catalog."default",
    feed_contact_email text COLLATE pg_catalog."default",
    feed_contact_url text COLLATE pg_catalog."default",
    CONSTRAINT feed_info_pkey PRIMARY KEY (feed_publisher_name),
    CONSTRAINT valid_feed_lang CHECK (is_valid_lang_code(feed_lang)),
    CONSTRAINT valid_default_lang CHECK (default_lang IS NULL OR is_valid_lang_code(default_lang))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.feed_info
    OWNER to postgres;
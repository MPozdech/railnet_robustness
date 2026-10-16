DROP TABLE demand.ov_24;

CREATE TABLE demand.ov_24 (
    id                    SERIAL PRIMARY KEY,
    station               VARCHAR(100)   NOT NULL,
    reizigers_station     INTEGER,
    instappers_werkdag    INTEGER,
    instappers_zaterdag   INTEGER,
    instappers_zondag     INTEGER,
    uitstappers_werkdag   INTEGER,
    uitstappers_zaterdag  INTEGER,
    uitstappers_zondag    INTEGER
);
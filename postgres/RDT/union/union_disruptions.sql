CREATE TABLE disruptions.disruptions_combined AS
SELECT
    ROW_NUMBER() OVER (
        ORDER BY service_year, old_id
    ) AS id,

	rdt_id, ns_lines, rdt_lines, rdt_lines_id, rdt_station_names, rdt_station_codes, cause_nl, cause_en, statistical_cause_nl, statistical_cause_en, cause_group, start_time, end_time, duration_minutes

FROM (

    SELECT
        2023 AS service_year,
        id AS old_id,

        rdt_id, ns_lines, rdt_lines, rdt_lines_id, rdt_station_names, rdt_station_codes, cause_nl, cause_en, statistical_cause_nl, statistical_cause_en, cause_group, start_time, end_time, duration_minutes

    FROM disruptions.disruptions_23

    UNION ALL

    SELECT
        2024 AS service_year,
        id AS old_id,

        rdt_id, ns_lines, rdt_lines, rdt_lines_id, rdt_station_names, rdt_station_codes, cause_nl, cause_en, statistical_cause_nl, statistical_cause_en, cause_group, start_time, end_time, duration_minutes

    FROM disruptions.disruptions_24

    UNION ALL

    SELECT
        2025 AS service_year,
        id AS old_id,

        rdt_id, ns_lines, rdt_lines, rdt_lines_id, rdt_station_names, rdt_station_codes, cause_nl, cause_en, statistical_cause_nl, statistical_cause_en, cause_group, start_time, end_time, duration_minutes

    FROM disruptions.disruptions_25

) combined;

ALTER TABLE disruptions.disruptions_combined
ADD PRIMARY KEY (id);
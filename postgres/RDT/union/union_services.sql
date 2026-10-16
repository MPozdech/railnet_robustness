CREATE TABLE disruptions.services_combined AS
SELECT
    ROW_NUMBER() OVER (
        ORDER BY service_year, old_id
    ) AS id,

    "Service:RDT-ID",
    "Service:Date",
    "Service:Type",
    "Service:Company",
    "Service:Train number",
    "Service:Completely cancelled",
    "Service:Partly cancelled",
    "Service:Maximum delay",
    "Stop:RDT-ID",
    "Stop:Station code",
    "Stop:Station name",
    "Stop:Arrival time",
    "Stop:Arrival delay",
    "Stop:Arrival cancelled",
    "Stop:Departure time",
    "Stop:Departure delay",
    "Stop:Departure cancelled",
    "Stop:Platform change",
    "Stop:Planned platform",
    "Stop:Actual platform"

FROM (

    SELECT
        2023 AS service_year,
        id AS old_id,

        "Service:RDT-ID",
        "Service:Date",
        "Service:Type",
        "Service:Company",
        "Service:Train number",
        "Service:Completely cancelled",
        "Service:Partly cancelled",
        "Service:Maximum delay",
        "Stop:RDT-ID",
        "Stop:Station code",
        "Stop:Station name",
        "Stop:Arrival time",
        "Stop:Arrival delay",
        "Stop:Arrival cancelled",
        "Stop:Departure time",
        "Stop:Departure delay",
        "Stop:Departure cancelled",
        "Stop:Platform change",
        "Stop:Planned platform",
        "Stop:Actual platform"

    FROM disruptions.services_23

    UNION ALL

    SELECT
        2024 AS service_year,
        id AS old_id,

        "Service:RDT-ID",
        "Service:Date",
        "Service:Type",
        "Service:Company",
        "Service:Train number",
        "Service:Completely cancelled",
        "Service:Partly cancelled",
        "Service:Maximum delay",
        "Stop:RDT-ID",
        "Stop:Station code",
        "Stop:Station name",
        "Stop:Arrival time",
        "Stop:Arrival delay",
        "Stop:Arrival cancelled",
        "Stop:Departure time",
        "Stop:Departure delay",
        "Stop:Departure cancelled",
        "Stop:Platform change",
        "Stop:Planned platform",
        "Stop:Actual platform"

    FROM disruptions.services_24

    UNION ALL

    SELECT
        2025 AS service_year,
        id AS old_id,

        "Service:RDT-ID",
        "Service:Date",
        "Service:Type",
        "Service:Company",
        "Service:Train number",
        "Service:Completely cancelled",
        "Service:Partly cancelled",
        "Service:Maximum delay",
        "Stop:RDT-ID",
        "Stop:Station code",
        "Stop:Station name",
        "Stop:Arrival time",
        "Stop:Arrival delay",
        "Stop:Arrival cancelled",
        "Stop:Departure time",
        "Stop:Departure delay",
        "Stop:Departure cancelled",
        "Stop:Platform change",
        "Stop:Planned platform",
        "Stop:Actual platform"

    FROM disruptions.services_25

) combined;

ALTER TABLE disruptions.services_combined
ADD PRIMARY KEY (id);
# Dutch Rail Network Disruption Analysis

Graph-based resilience analysis of the Dutch railway network, built for my MSc thesis.
The script constructs several linked network representations of the Dutch rail system,
assigns passenger demand to them with a calibrated gravity model, simulates disruptions
element-by-element under different bus-replacement scenarios, and tests which network
centrality measures best predict real-world disruption impact.

The graphs are constructed using *General Transit Feed Specification* (GTFS) and publicly 
available demand and network data from *Nederlandse Spoorwegen* (NS) and OV Oost. From the 
NS data a graph of the physical track connections is created -- the *track graph* -- and 
from the GTFS data a graph of the operated services is created -- the *service graph*.
Data about historical disruptions and services was taken from *Rijden de Treinen* (RDT). 
The source, dates of access, and limitations of each of these datasets are explained in
the section [Data](#data). 

To investigate how constructing new track alignments would improve robustness the following
lines of track were added to the track graph and assessed using the same measure - metric
procedure following targeted disruptions to the network: 
 - the Lelylijn (with and without the Groningen extension),
 - the Nedersaksenlijn, and
 - the Afsluitdijk alignment. 

## Order of operations

There are two primary parts to this project:
1. The preparation of the service and disruption data in PostgreSQL.
2. The execution of the disruption analysis in Python. 

For the PostgreSQL part it is possible to further divide the parts into multiple parts:
- The creation of the (train) service edgelist.
- The loading of the RDT disruption and historical service data. 
- The creation of the line bus and bus-replacement service graphs.
- The calculation of population catchments.

To run the project from scratch it is necessary to follow the subsequent steps:

### Service data
1. Create the GTFS PostgreSQL tables using the .sql scripts under postgres/GTFS/loading
2. Import the GTFS data from .txt under data/GTFS into their PostgreSQL tables.
3. Create the *master_routes* table using the master_routes.sql script under postgres/GTFS/service_edgelist
   - This creates a table where one row = one route going in one direction.
   - Includes the most commonly observed stops for this service and the travel times between them.
   - See the comments in this script for further information.
4. Create the *node_pairs* table using the node_pairs.sql script under postgres/GTFS/service_edgelist
   - This creates a table -- an undirected edgelist -- where one row = one edge in the service graph.
   - Each edge has a travel time and the route_ids of all routes passing over it.
### Disruption data
5. Create the RDT disruption, service, and station tables using the .sql scripts under postgres/RDT/loading
6. Load the data from the .csv under data/RDT into their PostgreSQL tables.
7. Combine the disruption and service into singular tables using the scripts under postgres/RDT/union
8. Create the *d25_pairs* table using the d25_pairs.sql script under postgres/RDT/services
   - This builds on the *node_pairs* table by adding the data about disruptions along these service edges.
   - It assumes that any record of a disruption with two stations in it also disrupted all stations between 
      these those in the record, e.g., a disruption record with (Hengelo, Enschede) also disrupted Enschede Kennispark.
   - See the comments in this script for further information.
9. Create the *disruption_replacement_services* table using the disruption_replacement_services.sql script under postgres/RDT/services
   - This is a directed edgelist where 1 row = 1 replacement service that was operated.
10. Create the *disrupted_services_combined* table using the disrupted_services_combined.sql script under postgres/RDT/services
   - This calculates how many services were operated across the 3 years for every service edge and how many of those were cancelled.
### Alternative transportation data
11. Create the *ipv_services* table using the ipv_services.sql script under postgres/RDT/services
   - This is a directed edgelist where 1 row = 1 (bus) replacement service was operated between two stations
12. Create the *ov_station_edgelist* table using the ov_station_edgelist.sql script under postgres/RDT/services
   - This is a directed edgelist where 1 row = 1 direct connection possible between two train stations using a line bus service.
   - All non-heavy rail modes are considered here (tram, metro, bus, buurtbus, etc.)
   - Travel time is assigned to every edge based on the time taken to traverse between the two train stations.
### Demand data
13. Create the OV Oost demand table using the .sql script under postgres/demand/ov_24.sql
14. Import the OV Ooost demand data from .txt under data/demand/train_2024.csv
15. Import the processed population data living in each station's catchment area from data/demand/clipped_pc4_population.shp into PostgreSQL.
   - The shapes contained with were found by taking the Voronoi polygons from each train station and then
      cutting out non-overlapping radii of 2km from each station node.
   - This same process was repeated for the stations which would be built in the different intervention scenarios.
16. Create the *catchments* table using the .sql script under postgres/demand/station_catchments.sql


## What it does

1. **Graph construction** — builds four graphs from the input datasets:
   - *Track graph*: physical rail infrastructure (NS segment data), edges weighted by
     travel time, length, and passenger flow.
   - *Service graph*: station-to-station train services (GTFS), each edge annotated with
     the underlying track path it traverses.
   - *IPV graph*: historical rail-replacement bus services (Rijden de Treinen archive, 2023–2025).
   - *OV graph*: the regular public bus network that parallels rail segments.
2. **Demand assignment** — distributes observed passenger demand across the network with a
   single-constrained gravity model (decay calibrated by minimizing log-RMSE against known
   NS flows), so every edge carries a modeled passenger flow, either for 24hrs or the morning 2hr peak.
3. **Disruption experiments** — removes every edge, node, and *block* (the track section
   between adjacent block stations, disrupted as a unit) one at a time, and recomputes
   a many structural and passenger-weighted metrics under three scenarios:
   - no alternative transport
   - historical rail-replacement (IPV) buses
   - the regular line bus network
4. **Correlation analysis** — Spearman rank correlation (with permutation-test p-values)
   between static centrality measures (betweenness, eigenvector, closeness, PageRank) and
   the measured per-element disruption impact, to evaluate how well cheap-to-compute
   measures predict expensive-to-simulate impacts.
5. **Intervention scenarios** — adds proposed new rail lines (Lelylijn, Nedersaksenlijn,
   Afsluitdijk link) to the network, reassigns demand, and quantifies how each proposal
   changes the network's disruption response for targeted corridors.

## Project structure

```
main.py                      # Full pipeline: construction -> demand -> disruptions -> correlations -> interventions
modules/
  data_preparation.py        # PostgreSQL/JSON imports, table joins, graph construction, block creation
  demand.py                  # Gravity model: calibration, flow assignment, diagnostics
  disruptions.py             # Edge/node/block disruption loops, targeted disruptions, correlation calc
  metrics.py                 # Per-disruption metric suite (APL variants, efficiency, connectivity, ...)
  measures.py                # Static centrality measures (betweenness, eigenvector, closeness, PageRank)
  interventions.py           # New-line scenarios: graph extension, demand re-assignment, targeted comparison
  plotting.py                # All figure generation (saved to figures/)
  supporting_functions.py    # Shared helpers (graph<->dataframe, ranking, value mapping)
```

## Data

The pipeline reads from a local PostgreSQL database containing:
- GTFS service data for 2026 from OVapi (accessed 02/02/26)
- RDT station data
- RDT disruption and service for 2023,2024,2025
- Public transit demand data from OV Oost
- Population catchments used to calculate demand for unknown stations

The GTFS and RDT data was manipulated in PostgreSQL and is loaded as an edgelist. 

The NS data is loaded from a JSON accessed from their [dashboard](https://dashboards.nsjaarverslag.nl/reizigersgedrag).

## Running

```bash
pip install -r requirements.txt
python main.py
```

Behaviour is controlled by the flags at the top of `main.py`:

| Flag | Effect |
|---|---|
| `RUN_EDGE_EXP` / `RUN_NODE_EXP` / `RUN_BLOCK_EXP` | Re-run the disruption simulations (slow) or load the cached results from `export/` |
| `ASSIGN_DEMAND` | Re-calibrate the gravity model from scratch |
| `MORNING_DEMAND` | Use morning-peak demand instead of 24h totals |
| `plotting.show_plots` | Pop figures in a viewer window (they are always saved to `figures/` regardless) |

Each disruption experiment caches its full results as JSON in `export/`.

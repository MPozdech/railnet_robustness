# Dutch Rail Network Disruption Analysis

Graph-based robustness analysis of the Dutch railway network, built for my MSc thesis.
This project constructs several linked network representations of the Dutch rail system,
assigns passenger demand to them with a calibrated gravity model, simulates disruptions
element-by-element under different bus-replacement scenarios, and tests which network
centrality measures best predict real-world disruption impact.

The graphs are constructed using *General Transit Feed Specification* (GTFS) and publicly 
available demand and network data from *Nederlandse Spoorwegen* (NS) and OV Oost. From the 
NS data a graph of the physical track connections is created—the *track graph*—and 
from the GTFS data a graph of the operated services is created—the *service graph*.
These graphs are the foundation on which all of the work is based around.
Data about historical disruptions and services was taken from *Rijden de Treinen* (RDT). 
The source, date of access, and description of each of these datasets are explained in
the section [Data sources](#data). 

To investigate how constructing new track alignments would improve robustness three new 
track corridors were added to the track graph and assessed using the same measure - metric
procedure following targeted disruptions to the network. These new track sections are the 
Nedersaksenlijn, the Lelylijn, and an bridge across the Afsluitdijk.

## What it does

1. **Edgelist construction** — takes the raw data and processes it into edgelists
   where 1 row = 1 edge in a graph. This is done for 3 different datasets:
   - *GTFS*: Planned service data for 2026 is turned into an edgelist by selecting the most 
      frequent stop order and travel time for each route.
   - *Replacement services*: The RDT data contains information about services that
      were operated as replacements for cancelled train services.
   - *Regular line services*: The same GTFS dataset is used to find normal, scheduled
      line (bus) services that operate in the country.
2. **Historical disruptions** — maps recorded disruptions from RDT to the service edge
      on which they occured. Assumes worst-case scenarios where a disruption between two
      Sprinter (SPR) stations also disrupted InterCity (IC) services as well.
3. **Population catchments** — calculates the population present in a catchment area around
      every train station in the country, creating the groundwork for later fitting of demand
      at potential new stations.
4. **Graph construction** — builds four graphs from the input datasets:
   - *Track graph*: physical rail infrastructure (NS segment data), edges weighted by
     travel time, length, and passenger flow.
   - *Service graph*: station-to-station train services (GTFS), each edge annotated with
     the underlying track path it traverses.
   - *IPV graph*: historical rail-replacement bus services (Rijden de Treinen archive, 2023–2025).
   - *OV graph*: the regular public bus network that parallels rail segments.
5. **Demand assignment** — distributes observed passenger demand across the network with a
   single-constrained gravity model (decay calibrated by minimizing log-RMSE against known
   NS flows), so every edge carries a modeled passenger flow, either for 24hrs or the morning 2hr peak.
6. **Disruption experiments** — removes every edge, node, and *block* (the track section
   between adjacent block stations, disrupted as a unit) one at a time, and recomputes
   a many structural and passenger-weighted metrics under three scenarios:
   - no alternative transport
   - historical rail-replacement (IPV) buses
   - planned regular transit line network (OV) services
7. **Correlation analysis** — Spearman rank correlation (with permutation-test p-values)
   between static centrality measures (betweenness, eigenvector, closeness, PageRank) and
   the measured per-element disruption impact, to evaluate how well cheap-to-compute
   measures predict expensive-to-simulate impacts.
8. **Intervention scenarios** — adds proposed new rail lines to the network, reassigns demand, 
   and quantifies how each proposal changes the network's disruption response for targeted corridors.

## Limitations
- **The model is static.** The graph model can only simulate two moments in time: one where the network is operating normally, 
   and one where it was disrupted. The progression of time is not considered, meaning it does not simulate how passengers may
   build up at a station due to a cancellation or how the operational schedule would have to be adjusted to account for a train
   falling out. A disruption only involves the removal of an edge from the graph and assumming the rest of the network stays
   the same. It lacks any insight into how the impacts of a disruption progress through time—it only provides a snapshot of a two hour period.

   *Risk*: An underestimation of impacts due to a lack of consideration for follow-on effects following a disruption.
- **Station demand is assumed to be linearly related to the population within that station's catchment area.**
   This includes the assumption that the population in a postcode is uniformly spread across said postcode and that
   IC stations have the same attraction as SPR stations. This extrapolation process resulted in a linear equation
   with a fitness of \(R^2 = 0.43\).

   *Risk*: Innaccurate estimation of passenger demand at stations where travel demand is unknown (SPR stations in Limburg and in the northern provinces).
- **Demand flow is based only on 24hr NS passenger traffic.** Flows are only known for around 67% of all edges in the network, these are then
   used to fit a gravity model. This model has a fitness a \(R^2 = 0.73\) and a \(RMSE = 6653 pax\), 
   which implies a good fit but deviate significantly from observed flows.

   *Risk*: Innaccurate demand flows, causing innaccuate importance and impact results.
- **Demand is not recalculated during disruptions.** Following a disruption the flow across a disrupted edge is 
   assumed to be the same as if it was normally operating. Flows are not recalculated after a disruption due to 
   unreasonably high computation time required. This includes overall travel demand not being recalculated due to
   additional travel time cost required to transfer services or change modes.
   
   *Risk*: The demand across an edge is overestimated for the disrupted link and underestimated for other undisrupted links.
- **Transfer times are not considered.** There is no travel time penalty associated with changing services or modes—passengers are assummed to 
   immediately transfer to a waiting service that departs immediately. For node-pairs (trips) that are directly connected by a service this doesn't matter,
   but for trips that involve transfers this causes a significant discrepancy with reality, increasing as the number of transfers increase.

   *Risk*: This results in an underestimation of actual travel time, potentially leading to a better image of the network than what exists in reality.
- **The underlying non-heavy rail public transit network was not simulated.** Regular line services were only considered as alternative
   links between train stations. Their actual, entire networks were not simulated. What an "OV alternative" for a link means is that
   the travel time between two train stations was increased to the travel time it would take to go by bus between these two stations.
   This means passenger behaviour such as taking a bus to go betweenn two separate train lines is not considered.

   *Risk*: Enabling passengers to transfer between train lines can lead to over/underestimation of demand on the edges.
- **All transit line modes were considered as viable alternatives.** By considering modes like buurtbuses (very infrequent and
   low-capacity services) the number of alternative options is higher that what may actually be realistic for passengers to use
   as alternative travel options. When selecting these alternatives they were limited to those leaving at least once in the period from
   7am to 10am, but some of those services did only have one departure in that time window.

   *Risk*: The number of alternative connections is overestimated, leading to an underestimation of impacts.
- **Node measures are averaged to get a value for an edge.** When calculating the correlation between the removal of an edge with the
   a measure that only outputs results for nodes the average between two nodes is assigned as the measure value for an edge. This flattens
   the values, reducing the important of any one individual node. This is similarly done for blocks—sets of nodes and edges—when they are disrupted.

   *Risk*: Incorrect assessment of explanatory power for the measures due to a loss of information. 

## Project set-up

There are two primary parts to this project:
1. The preparation of the input data in a (local) PostgreSQL database.
2. The execution of the simulation analysis in Python. 

For the PostgreSQL part it is possible to further divide the parts into multiple parts, 
these are highlighted in the list below. To run the project from scratch it is necessary 
to follow these steps in order, starting with loading the data into a PostgreSQL database:

### Service data
1. Create the GTFS PostgreSQL tables using the .sql scripts under `postgres/GTFS/loading`
2. Import the GTFS data from .txt under data/GTFS into their PostgreSQL tables.
3. Create the *master_routes* table using the script `postgres/GTFS/services/master_routes.sql`
   - This creates a table where one row = one route going in one direction.
   - Includes the most commonly observed stops for this service and the travel times between them.
   - See the comments in this script for further information.
4. Create the *node_pairs* table using the script `postgres/GTFS/services/node_pairs.sql`
   - This creates a table -- an undirected edgelist -- where one row = one edge in the service graph.
   - Each edge has a travel time and the route_ids of all routes passing over it.
### Disruption data
5. Create the RDT disruption, service, and station tables using the .sql scripts under `postgres/RDT/loading`
6. Load the data from the .csv under `data/RDT` into their PostgreSQL tables.
7. Combine the disruption and service into singular tables using their scripts `postgres/RDT/union`
8. Create the *d25_pairs* table using the script `postgres/RDT/services/d25_pairs.sql`
   - This builds on the *node_pairs* table by adding the data about disruptions along these service edges.
   - It assumes that any record of a disruption with two stations in it also disrupted all stations between 
      these those in the record, e.g., a disruption record with (Hengelo, Enschede) also disrupted Enschede Kennispark.
   - See the comments in this script for further information.
9. Create the *disruption_replacement_services* table using the script `postgres/RDT/services/disruption_replacement_services.sql`
      - This is a list where 1 row = 1 replacement service that was operated.
10. Create the *disrupted_services_combined* table using the script `postgres/RDT/services/disrupted_services_combined.sql`
      - This calculates how many services were operated across the 3 years for every service edge and how many of those were cancelled.
### Alternative transportation data
11. Create the *ipv_services* table using the script `postgres/RDT/services/ipv_services.sql`
      - This is a directed edgelist where 1 row = 1 (bus) replacement service was operated between two stations
12. Create the *ov_station_edgelist* table using the script `postgres/RDT/services/ov_station_edgelist.sql`
      - This is a directed edgelist where 1 row = 1 direct connection possible between two train stations using a line bus service.
      - All non-heavy rail modes are considered here (tram, metro, bus, buurtbus, etc.)
      - Travel time is assigned to every edge based on the time taken to traverse between the two train stations.
### Demand data
13. Create the OV Oost demand table using the script `postgres/demand/ov_24.sql`
14. Import the OV Ooost demand data from `data/demand/train_2024.csv`
15. Import the processed population data living in each station's catchment area from `data/demand/clipped_pc4_population.shp` into PostgreSQL.
      - The shapes contained with were found by taking the Voronoi polygons from each train station and then
      cutting out non-overlapping radii of 2km from each station node.
      - This same process was repeated for the stations which would be built in the different intervention scenarios.
16. Create the *catchments* table using the script `postgres/demand/station_catchments.sql`
      - Built on top of the Centraal Bureau voor de Statistiek's dataset on population within postcodes—see [Data sources](#data).
      - This process assumes a proportional relationship between area and population in a postcode area, meaning
         the population is uniformly distributed across the postcode polygon.

This concludes the preparation required through PostgreSQL, with the remainder of the project being executed
via the Python script `main.py`. The script itself contains the entire process from the construction to the intervention
analysis, with results being exported as figures and JSONs. 

### Python running

```bash
pip install -r requirements.txt
python main.py
```

Behaviour is controlled by the flags at the top of `main.py`:

| Flag | Effect |
|---|---|
| `plotting.show_plots` | Pop figures in a viewer window (they are always saved to `figures/` regardless) |
| `plotting.plot_dpi` | What DPI the figures will be rendered in |
| `demand.optimize` | Re-calibrate the gravity model from scratch |
| `demand.decay` / `demand.scale_factor` | (Initial) Gravity function parameters |
| `MORNING_DEMAND` | Use morning-peak demand instead of 24h totals |
| `RUN_EDGE_EXP` / `RUN_NODE_EXP` / `RUN_BLOCK_EXP` | Re-run the disruption simulations (slow) or load the cached results from `export/` |
| `EXPORT` | Export the metric and correlation tables to .csv |
| `CAPACITY_IPV_BUS` / `CAPACITY_OV_BUS` | Capacity of the alternative vehicles |
| `DEFAULT_HEADWAY` | Fallback if no headway was observed in the GTFS / IPV database |
| `TARGET1` / `TARGET2` | The edge between these two nodes is targeted for disruption testing. |

Each disruption experiment caches its full results as JSON in `export/`.


## Project structure

```
main.py                                      # Full pipeline: construction -> demand -> disruptions -> correlations -> interventions
modules/
  data_preparation.py                        # PostgreSQL/JSON imports, table joins, graph construction, block creation
  demand.py                                  # Gravity model: calibration, flow assignment, diagnostics
  disruptions.py                             # Edge/node/block disruption loops, targeted disruptions, correlation calc
  metrics.py                                 # Per-disruption metrics (APL variants, efficiency, connectivity, etc.)
  measures.py                                # Static centrality measures (betweenness, eigenvector, closeness, PageRank)
  interventions.py                           # New-line scenarios: graph extension, demand re-assignment, targeted comparison
  plotting.py                                # All figure generation (saved to figures/)
  supporting_functions.py                    # Shared helpers (graph<->dataframe, ranking, value mapping)
data/
   demand/
      2024_demand_data.json                  # Demand and network data from NS
      clipped_pc4_population.shp             # Shapefile containing the catchment areas
      train_2024.csv                         # Demand data from OV Oost
postgres/
   demand/
      ov_24.sql                              # Scripts for creating the ov_24 table
      station_catchments.sql                 # Calculates the population in a station's catchment area
   GTFS/
      loading/                               # Table creation scripts for the different GTFS tables
      services/
         master_routes.sql                   # Extracts orders of stops and travel times for all heavy-rail routes in GTFS
         node_pairs.sql                      # Creates a directed edgelist from the master_routes table
   RDT
      loading/                               # Scripts for creating the RDT tables
      services/
         d25_pairs.sql                       # Attach disruption data to the node_pairs table
         disrupted_services_combined.sql     # Counts the number of services operated in total and the number of those that were cancelled
         disruption_replacement_services.sql # Extracts all IPV services that were operated
         ipv_services.sql                    # Creates a directed edgelist from the replacement services
         ov_station_edgelist.sql             # Creates a directed edgelist from direct OV services between two train stations.
      union/                                 # Joins the individual year tables into one combined table for disruptions and services.
```

## Data sources

| Name | Source | Accessed | Description |
|---|---|---|---|
| NS demand and network | [Link](https://dashboards.nsjaarverslag.nl/reizigersgedrag?dtYear=2024) | 23/02/26 | Station passenger demand and flow across track segments |
| GTFS services | [Link](https://gtfs.ovapi.nl/) | 21/01/26 | Passenger services planned to operate in 2026 |
| RDT disruptions | [Link](https://www.rijdendetreinen.nl/en/open-data/disruptions#downloads) | 02/02/26 | Historical disruptions recorded |
| RDT services | [Link](https://www.rijdendetreinen.nl/en/open-data/train-archive#downloads) | 11/03/26 | Historical services operated |
| Station details | [Link](https://www.rijdendetreinen.nl/en/open-data/stations#downloads) | 02/02/26 | Station size, code, type |
| OV Oost demand | [Link](https://app.powerbi.com/view?r=eyJrIjoiZTllZGUzNzgtZDM2NS00ZmZiLWIyZDAtZjk0YWE4ODQ2MGViIiwidCI6Ijk1ZjNhN2Q4LTczMGMtNGYzNS1hOTA5LTg2N2QzZmJkZThmZSIsImMiOjh9) | 25/03/26 | Station ridership across the provinces of Gelderland and Overijssel.
| CBS Population data | [Link](https://www.cbs.nl/nl-nl/dossier/nederland-regionaal/geografische-data/gegevens-per-postcode) | 24/02/26 | Number of inhabitats per level 4 postcode (PC4) |

## Analysis

Their are two types of results that this script provides:
1. The graph measures
2. The metric impacts

The specific measures and metrics, and how they are calculated, are listed out below.

### Measures
- **Betweenness** — calculates the number of shortest paths that pass through an element (node or edge). 
   High values indicate many node-pairs pass across an element.

   Normalized so the output is a fraction of the total number of node-pairs in the graph.

   Weighted by the edge attribute `travel_time`.

   Calculated using the NetworkX function [betweenness_centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.betweenness_centrality.html) for nodes and with 
   [edge_betweenness_centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.edge_betweenness_centrality.html#networkx.algorithms.centrality.edge_betweenness_centrality) for edges.
- **Closeness** — calculates the distance from a node to all other nodes to the network.
   High values indicate quicker access to all other nodes in the network.

   Weighted by the edge attribute `travel_time`.

   Calculated using the NetworkX function [closeness_centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.closeness_centrality.html#networkx.algorithms.centrality.closeness_centrality).
- **Eigenvector** — iterative calculation of a node's importance based on its neighbors. The premise is that high importance
   nodes are connected to other highly important nodes. Three alternatives of this centrality are considered:

   - *Unweighted*, where the network is assessed without any intial importance for the nodes and the edges are all equally strong.
   - *Initial importance only*, where the initial importance parameter `nstart` is set to the node attribute `TravellersPerDay`.
   - *Weighted*, where `nstart` is set to `TravellersPerDay` and the edge weight is set to the edge attribute `flow`. This simulates
      how edges with high demand are more important connections than edges with low passenger flows.

   This is calculated using the NetworkX function [eigenvector_centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.eigenvector_centrality.html#networkx.algorithms.centrality.eigenvector_centrality).
- **PageRank** — iterative calculation of a node's importance based on eigenvector centrality, but expanded by also considering
   the degree of a node, where nodes with high numbers of neighbors are considered as more important. By this process it also
   ensures every node has some value, in contrast with eigenvector centrality where most of the nodes will have near-zero values.
   The default dampening parameter `alpha` of 0.85 was used
   Two alternatives were calculated:

   - *Unweighted*, where the network is assessed without any intial importance for the nodes and the edges are all equally strong.
   - *Weighted*, where the `nstart` is set to `TravellersPerDay` and `weight` is set to `flow`.

   This is calculated using the NetworkX function [pagerank](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html).
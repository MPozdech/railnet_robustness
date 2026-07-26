# Dutch Rail Network Disruption Analysis

Graph-based resilience analysis of the Dutch railway network, built for my MSc thesis.
The script constructs several linked network representations of the Dutch rail system,
assigns passenger demand to them with a calibrated gravity model, simulates disruptions
element-by-element under different bus-replacement scenarios, and tests which network
centrality measures best predict real-world disruption impact.

Included as well is the testing of a number of rail interventions:
 - the Lelylijn (with and without the Groningen extension),
 - the Nedersaksenlijn, 
 - the Afsluitdijk alignment. 

These can be tested with targeted disruptions to the improved network. 

## What it does

1. **Graph construction** — builds four graphs from raw data:
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
  interventions.py           # New-line scenarios: graph extension, re-assignment, targeted comparison
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

import modules.supporting_functions as sf # type: ignore
import networkx as nx
import math
from scipy.optimize import minimize_scalar
import numpy as np
import time

"""
Functions that relate to the estimating of passenger flows
across all links where flow is not provided from NS "to_/from_travelers" value.

Contains a single-constrained gravity function (Only supply is considered)
Assumes attraction and supply is always at most half the demand. 

Calibration of the decay factor was done by minimizing log-RMSE as to reduce the effects of large
residuals on high-demand edges. 

Prefers using the "demand" value 
(either BoardingDeboardig for full-NS stations or 
BoardingDeboarding + reizeigers from OV-Oost data to try and avoid transfering demand)
If demand not available, uses fitted catchment -> ridership function ("TravelersPerDay")
"""

# Passed parameters
optimize = True
decay = None
scale_factor = None

def assign_flows(
    G: nx.Graph,
    decay: float = None,
    max_travel_time: float = None,
    scale_factor: float = None,
    apply_override: bool = True,
    morning_demand: bool = False
) -> nx.Graph:
    """
    Origin-constrained (production-constrained) gravity model.

    For each origin u, total outgoing trips are hard-constrained to O_u = demand_u / 2.
    The balancing factor A_u enforces this:

        T(u,v) = O_u * A_u * D_v * dist(u,v)^(-decay)

    where A_u = 1 / sum_{v} [ D_v * dist(u,v)^(-decay)]

    This guarantees sum_v T(u,v) = O_u for every origin u, regardless of decay or network topology.

    Flow accumulates on edges from ALL directed OD pairs whose shortest path traverses that edge. 
    On an undirected graph this means both T(u,v) along path u->v and T(v,u) along path v->u contribute to the same physical edge.

    This matches how the real data sees flow as the sum across both directions (to + from per track edge)

    Args:
        G               : NetworkX graph. Nodes carry 'demand' or 'TravelersPerDay', edges carry 'travel_time'.
        decay           : Power-law distance decay exponent (beta >= 0).
        max_travel_time : OD pairs with dist > this are ignored. None = no cutoff.
        scale_factor    : Global calibration scalar.
        apply_override  : If True, replaces modelled flow with observed 'to_travelers' where ground truth exists. 
                          Set False during calibration so the optimiser sees raw model output on every edge.
        morning_demand  : If true uses 'MorningDemand' to assign the morning peak demand instead of 24hr demand
    """
    # Fall back to the module-level decay / scale_factor
    if decay is None:
        decay = globals()['decay']
    if scale_factor is None:
        scale_factor = globals()['scale_factor']

    nx.set_edge_attributes(G, 0.0, "flow")

    # All-pairs shortest paths (distances + routes)
    all_pairs = dict(nx.all_pairs_dijkstra(G, weight="travel_time"))

    # Node productions O_u and attractions D_v
    def _get_od_weight(n: object) -> float | None:
        """Return demand/2 for node n, or None if node has no usable demand."""
        if morning_demand:
            m = G.nodes[n].get("MorningDemand")
            if m is not None and not math.isnan(m) and m > 0:  # was isnan(d) and d > 0
                return m / 2.0
        else:
            d = G.nodes[n].get("demand")
            if d is not None and not math.isnan(d) and d > 0:
                return d / 2.0
            t = G.nodes[n].get("TravelersPerDay")
            if t is not None and not math.isnan(t) and t > 0:
                return t / 2.0
        return None

    valid_nodes = [n for n in G.nodes if _get_od_weight(n) is not None]
    weights = {n: _get_od_weight(n) for n in valid_nodes}  # O_u = D_v for all nodes

    # Balancing factors A_u (one per origin)
    balancing_factors: dict = {}
    for u in valid_nodes:
        dists_u = all_pairs[u][0]
        denominator = 0.0
        for v in valid_nodes:
            if v == u:
                continue
            dist = dists_u.get(v)
            if dist is None or dist <= 0.0:
                continue
            if max_travel_time is not None and dist > max_travel_time:
                continue
            denominator += weights[v] * (dist ** -decay)

        # If a node is completely isolated, A_u stays 0 and it generates no trips.
        balancing_factors[u] = (1.0 / denominator) if denominator > 0.0 else 0.0

    # Flow assignment - iterate over origin-destination pairs
    od_matrix: dict[tuple, float] = {}
    for u in valid_nodes:
        A_u = balancing_factors[u]
        if A_u == 0.0:
            continue

        O_u   = weights[u]
        dists_u = all_pairs[u][0]
        paths_u = all_pairs[u][1]

        for v in valid_nodes:
            if v == u:
                continue
            dist = dists_u.get(v)
            if dist is None or dist <= 0.0:
                continue
            if max_travel_time is not None and dist > max_travel_time:
                continue

            # Gravity model (origin-constrained):
            T_uv = O_u * A_u * weights[v] * (dist ** -decay)

            od_matrix[(u, v)] = T_uv # add trips to OD matrix

            path = paths_u[v]
            for a, b in zip(path[:-1], path[1:]):
                G[a][b]["flow"] += T_uv * scale_factor

    # If true sets the real flow value to be the flow, otherwise use the modeled values 
    if apply_override:
        for u, v, data in G.edges(data=True):
            if G.nodes[u].get("Type") == "yard" or G.nodes[v].get("Type") == "yard":
                G[u][v]["flow"] = 0.0
                continue
            obs = data.get("real_flow")
            has_obs = obs is not None and not math.isnan(float(obs)) and obs > 0
            if has_obs:
                G[u][v]["flow"] = float(obs)

    # Calculate additional weights for each edge
    for u, v, data in G.edges(data=True):
        G[u][v]["pax_min"] = G[u][v]["flow"] * G[u][v]["travel_time"]
        G[u][v]["pax_over_min"] = G[u][v]["flow"] / G[u][v]["travel_time"]

    # Per-node OD totals (row sum + column sum = productions + attractions)
    # Stored as a node attribute so calibrate_decay can compare them against observed station demand without touching edge flows.
    node_od_total: dict = {}
    for (u, v), trips in od_matrix.items():
        node_od_total[u] = node_od_total.get(u, 0.0) + trips   # outgoing (production)
        node_od_total[v] = node_od_total.get(v, 0.0) + trips   # incoming (attraction)
    nx.set_node_attributes(G, node_od_total, "modelled_od_total")

    # Per-edge derived weights
    for u, v, data in G.edges(data=True):
        tt   = data.get("travel_time", 0.0)
        flow = G[u][v]["flow"]
        G[u][v]["pax_min"]      = flow * tt
        G[u][v]["pax_over_min"] = flow / tt if tt > 0 else 0.0

    return G

def calibrate_decay(
    G: nx.Graph,
    decay_bounds: tuple = (0.01, 5.0),
    loss_type: str = "log",
    morning_demand: bool = False,
    calib_target: str = "edges",
    joint_node_weight: float = 0.5,
) -> tuple:
    """
    Calibrates decay and scale_factor for the gravity model.

    Args:
        G                 : NetworkX graph with node demand attributes and edge 'travel_time' / 'to_/from_travelers'.
        decay_bounds      : (min, max) for the decay exponent.
        loss_type         : 'log'  - log-RMSE, treats proportional errors equally
                            'rmse' - standard RMSE in linear space
        morning_demand    : If True,  node observations come from 'MorningDemand'.
                            If False, node observations come from 'BoardingDeboarding'.
        calib_target      : 'edges' | 'nodes' | 'joint'  - only use edges, rest not good.
        joint_node_weight : Weight [0, 1] for the node component in joint mode. 0.0 = pure edge loss; 1.0 = pure node loss.
    Returns:
        (decay_opt, scale_factor)
    """

    obs_attr = "MorningDemand" if morning_demand else "BoardingDeboarding"

    # Collect observations for whichever target(s) are needed
    edge_obs_list:  list = []
    edge_observed:  np.ndarray = np.array([])
    node_obs_list:  list = []
    node_observed:  np.ndarray = np.array([])

    if calib_target in ("edges", "joint"):
        edge_obs_list = [
            (u, v) for u, v, d in G.edges(data=True)
            if d.get("real_flow") is not None
            and not math.isnan(float(d["real_flow"]))
            and d["real_flow"] > 0
        ]
        if len(edge_obs_list) == 0:
            raise ValueError(
                f"calib_target='{calib_target}' requires edges with 'real_flow' > 0, but none were found."
            )
        edge_observed = np.array([G[u][v]["real_flow"] for u, v in edge_obs_list])

    if calib_target in ("nodes", "joint"):
        node_obs_list = [
            n for n, d in G.nodes(data=True)
            if d.get("full_demand") == True
            and d.get(obs_attr) is not None
            and not math.isnan(float(d[obs_attr]))
            and float(d[obs_attr]) > 0
        ]
        node_observed = np.array([float(G.nodes[n][obs_attr]) for n in node_obs_list])

    start_time = time.time()
    print(f"Calibration started at: {time.strftime('%H:%M:%S')}")
    if calib_target in ("edges", "joint"):
        print(f"  Edge obs  : {len(edge_obs_list):4d} edges  "
              f"| range: {edge_observed.min():.0f} – {edge_observed.max():.0f}")
    if calib_target in ("nodes", "joint"):
        print(f"  Node obs  : {len(node_obs_list):4d} nodes (full_demand=True, '{obs_attr}')  "
              f"| range: {node_observed.min():.0f} – {node_observed.max():.0f}")
    if calib_target == "joint":
        print(f"  Joint weights : edge={1.0 - joint_node_weight:.2f}  "
              f"node={joint_node_weight:.2f}")
    print(f" Loss: {loss_type}  |  Target: {calib_target}")
    print(f"{'':->60}")

    G_work = G.copy()

    # Helper functions
    def _run_model(decay: float) -> None:
        nx.set_edge_attributes(G_work, 0.0, "flow")
        assign_flows(
            G_work, decay=decay, scale_factor=1.0, apply_override=False,
            morning_demand=morning_demand)

    def _get_modelled_edges() -> np.ndarray:
        return np.array([G_work[u][v]["flow"] for u, v in edge_obs_list])

    def _get_modelled_nodes() -> np.ndarray:
        return np.array([G_work.nodes[n].get("modelled_od_total", 0.0)
                         for n in node_obs_list])

    # Analytical scale factor for a given (observed, modelled) pair
    def _compute_scale(observed: np.ndarray, modelled: np.ndarray) -> float:
        if loss_type == "log":
            valid = modelled > 0
            if not valid.any():
                return 1.0
            return float(np.exp(np.mean(np.log(observed[valid]) - np.log(modelled[valid]))))
        else:
            denom = float(np.mean(modelled))
            return float(np.mean(observed)) / denom if denom > 0 else 1.0

    # Single-component loss helper
    def _component_loss(observed: np.ndarray, scaled_modelled: np.ndarray) -> float:
        if loss_type == "log":
            valid = scaled_modelled > 0
            if not valid.any():
                return float("inf")
            return float(np.sqrt(np.mean(
                (np.log(scaled_modelled[valid]) - np.log(observed[valid])) ** 2
            )))
        else:
            return float(np.sqrt(np.mean((scaled_modelled - observed) ** 2)))

    # Loss function passed to the optimiser
    #   "edges" - scale anchored to edges, loss purely on edges.
    #   "nodes" - scale anchored to nodes, loss purely on nodes.
    #   "joint" - scale anchored to edges, weighted sum of edge + node losses.
    iteration = [0]

    def _loss_fn(decay: float) -> float:
        iter_start = time.time()
        _run_model(decay)

        if calib_target == "edges":
            mod_e  = _get_modelled_edges()
            scale  = _compute_scale(edge_observed, mod_e)
            loss   = _component_loss(edge_observed, mod_e * scale)

        elif calib_target == "nodes":
            mod_n  = _get_modelled_nodes()
            scale  = _compute_scale(node_observed, mod_n)
            loss   = _component_loss(node_observed, mod_n * scale)

        else:  # joint
            mod_e  = _get_modelled_edges()
            mod_n  = _get_modelled_nodes()
            # Scale is always anchored to edges so it stays consistent
            # with the scale_factor applied to edge flows downstream.
            scale      = _compute_scale(edge_observed, mod_e)
            edge_loss  = _component_loss(edge_observed, mod_e * scale)
            node_loss  = _component_loss(node_observed, mod_n * scale)
            loss = (1.0 - joint_node_weight) * edge_loss + joint_node_weight * node_loss

        iteration[0] += 1
        elapsed = time.time() - start_time
        print(
            f"  Iter {iteration[0]:4d} | "
            f"decay: {decay:.4f} | "
            f"scale: {scale:.4f} | "
            f"loss ({loss_type}/{calib_target}): {loss:.4f} | "
            f"iter: {time.time() - iter_start:.1f}s  elapsed: {elapsed:.0f}s"
        )
        return loss

    # Optimise decay, 1-D bounded scalar search
    result = minimize_scalar(
        _loss_fn,
        bounds=decay_bounds,
        method="bounded",
        options={"xatol": 1e-4, "maxiter": 200},
    )

    decay_opt = float(result.x)

    # Final scale factor at optimal decay
    _run_model(decay_opt)
    if calib_target == "nodes":
        scale_factor = _compute_scale(node_observed, _get_modelled_nodes())
    else: 
        scale_factor = _compute_scale(edge_observed, _get_modelled_edges())

    total_time = time.time() - start_time
    print(f"{'':->60}")
    print(f"Calibration finished at: {time.strftime('%H:%M:%S')}  (total: {total_time:.0f}s)")
    print(f"Optimal decay   : {decay_opt:.4f}")
    print(f"Scale factor    : {scale_factor:.6f}")
    print(f"Converged       : {result.success}  ({result.message})")

    return decay_opt, scale_factor

def diagnose_flows(G: nx.Graph, label: str = "", test_flows: bool = False, morning_demand:bool = False):
    """
    Prints summary statistics comparing modelled values to observed ground truth.

    Args:
        G          : Graph after flow assignment.
        label      : Printed in the summary header.
        test_flows : If True,  compare edge 'flow' vs edge 'real_flow'.
                     If False, compare node 'modelled_od_total' vs node 'BoardingDeboarding'
    """
    if test_flows:
        observed_edges = [
            (u, v) for u, v, d in G.edges(data=True)
            if d.get("real_flow") is not None
            and not math.isnan(float(d["real_flow"]))
            and d["real_flow"] > 0
            and d.get("flow") is not None
            and d["flow"] > 0
        ]
        observed = np.array([G[u][v]["real_flow"] for u, v in observed_edges])
        modelled = np.array([G[u][v]["flow"]         for u, v in observed_edges])
    else:
        if morning_demand:
            target = "MorningDemand"
        else:
            target = "BoardingDeboarding"
        observed_edges = [
            u for u, d in G.nodes(data=True)
            if d.get(target) is not None # The % value from ns used as observed values
            and not math.isnan(float(d[target]))
            and d[target] > 0
            and d.get("modelled_od_total") is not None
            and d["modelled_od_total"] > 0
        ]
        observed = np.array([G.nodes[u][target]  for u in observed_edges])
        modelled = np.array([G.nodes[u]["modelled_od_total"]   for u in observed_edges])

    residuals = modelled - observed

    r2   = 1 - np.sum(residuals ** 2) / np.sum((observed - np.mean(observed)) ** 2)
    rmse = np.sqrt(np.mean(residuals ** 2))

    print(f"\n--- RMSE by demand magnitude ---")
    for lo, hi in [(0, 2000), (2000, 5000), (5000, 10000), (10000, 15000), (15000, 30000), (30000, 50000), (50000, 999999)]:
        mask = (observed >= lo) & (observed < hi)
        if mask.sum() == 0:
            continue
        print(
            f"  {lo:6d}-{hi:6d} pax | n={mask.sum():3d} | "
            f"RMSE: {np.sqrt(np.mean(residuals[mask]**2)):7.0f} | "
            f"bias: {np.mean(residuals[mask]):+.0f}"
        )

    if test_flows:
        print(f"\n--- Worst 15 edges by absolute residual ---")
        for (u, v), obs, mod, res in sorted(
            zip(observed_edges, observed, modelled, residuals),
            key=lambda x: abs(x[3]), reverse=True
        )[:15]:
            print(
                f"  {u:30s} -> {v:30s} | "
                f"obs: {obs:6.0f}  mod: {mod:6.0f}  resid: {res:+.0f} ({abs(res)/obs*100:.0f}%)"
            )
        print(f"\n--- Worst 15 edges by percentage residual ---")
        for (u, v), obs, mod, res in sorted(
            zip(observed_edges, observed, modelled, residuals),
            key=lambda x: abs(x[3]) / x[1], reverse=True
        )[:15]:
            print(
                f"  {u:30s} -> {v:30s} | "
                f"obs: {obs:6.0f}  mod: {mod:6.0f}  resid: {res:+.0f} ({abs(res)/obs*100:.0f}%)"
            )
    else:
        print(f"\n--- Worst 15 nodes by absolute residual ---")
        for u, obs, mod, res in sorted(
            zip(observed_edges, observed, modelled, residuals),
            key=lambda x: abs(x[3]), reverse=True
        )[:15]:
            print(
                f"  {str(u):40s} | "
                f"obs: {obs:6.0f}  mod: {mod:6.0f}  resid: {res:+.0f} ({abs(res)/obs*100:.0f}%)"
            )
        print(f"\n--- Worst 15 nodes by percentage residual ---")
        for u, obs, mod, res in sorted(
            zip(observed_edges, observed, modelled, residuals),
            key=lambda x: abs(x[3]) / x[1], reverse=True
        )[:15]:
            print(
                f"  {str(u):40s} | "
                f"obs: {obs:6.0f}  mod: {mod:6.0f}  resid: {res:+.0f} ({abs(res)/obs*100:.0f}%)"
            )

    print(f"\n--- Overall accuracy metrics for {label} ---")
    print(f"  R²:               {r2:.4f}")
    print(f"  RMSE:             {rmse:.0f} pax")
    print(f"  Median residual:  {np.median(residuals):+.0f} pax")
    print(f"  % within 25%:     {100*np.mean(np.abs(residuals)/observed < 0.25):.1f}%")
    print(f"  % within 50%:     {100*np.mean(np.abs(residuals)/observed < 0.50):.1f}%")

def flow_assignment(infra:nx.Graph, services:nx.Graph, decay:float=None, scale_factor:float=None, verbose:bool = False, morning_demand:bool = False) -> nx.Graph:
    """
    Wrapper function for flow assignemnt

    All optimization and evaluation is done on the 24hr flows, but the outputs to the infra_ and services_model can be in peak flow. 
    I'm assuming they can be transfered. 

    Args:
        infra: track graph
        services: service graph
        optimize: True if want to run optimization procedure. False by default
        verbose: True if want to print the performance of the assignment. False by default
        morning_demand: True if want infra_model & services_model to have MorningPeak demand flows
    Returns:
        The 3 graphs for:
            infra_mixed (both ns and model flows) ! THIS IS ONLY AVAILABLE FOR 24HR !, 
            infra_model (only model flows), and 
            services_model
    """


    # Take main parameters unless passed otherwise
    if decay is None:
        decay = globals()['decay']
    if scale_factor is None:
        scale_factor = globals()['scale_factor']

    if optimize:
        decay, scale_factor = calibrate_decay(infra, loss_type='log', morning_demand=False, calib_target='edges')
        verbose = True

    print(f'Assigning flows to graph, 1/3')
    infra_mixed_single    = assign_flows(infra.copy(),       decay=decay, scale_factor=scale_factor, apply_override=True,  morning_demand=False) # This one prefers NS flows, if not available uses modeled flows. Only for 24hr demand!
    print(f'Assigning flows to graph, 2/3')
    infra_model_single    = assign_flows(infra.copy(),       decay=decay, scale_factor=scale_factor, apply_override=False, morning_demand=morning_demand)
    print(f'Assigning flows to graph, 3/3')
    services_model_single = assign_flows(services.copy(),    decay=decay, scale_factor=scale_factor, apply_override=False, morning_demand=morning_demand)
    if verbose:
        infra_model_test = assign_flows(infra.copy(),        decay=decay, scale_factor=scale_factor, apply_override=False, morning_demand=False)
        service_model_test = assign_flows(services.copy(),   decay=decay, scale_factor=scale_factor, apply_override=False, morning_demand=False)
        print("Node destination sum / BoardingDeboarding from infra model")
        diagnose_flows(infra_model_test, test_flows=False, morning_demand=False)
        print("Flow calculation / to_travelers from infra model")
        diagnose_flows(infra_model_test, test_flows=True, morning_demand=False)
        print("Node destination sum / BoardingDeboarding from infra model")
        diagnose_flows(service_model_test, test_flows=False, morning_demand=False)
    return infra_mixed_single, infra_model_single, services_model_single
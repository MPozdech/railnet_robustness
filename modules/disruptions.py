import modules.metrics as metrics           # type: ignore
import modules.supporting_functions as sf   # type: ignore
import modules.demand as demand
import pandas as pd
import networkx as nx
import numpy as np
from scipy import stats
from collections import defaultdict
import itertools
import ast
import json
import time

"""
This handles everything related to disruptions.

Edge disruptions, node disruptions, block disruptions, targeted disruption.

Each have track and service values calculated. 

Includes some supporting functions; correlation process used later to compare the disruptions with the measures 
"""

def _get_subgraph(G: nx.Graph, morning_demand:bool=True,return_only_subgraph:bool=False):
    """
    Get the largest connected subgraph and store stats for the disconnected parts 
    """
    components = list(nx.connected_components(G)) # list of graph components
    n_components = len(components)                # how many components post-disruption
    largest_cc_nodes = max(components, key=len)   # list of nodes in the largest component
    n_nodes_largest = len(largest_cc_nodes)       # how many nodes in the largest component
    largest_sg = G.subgraph(largest_cc_nodes).copy() # create graph from the largest component
    
    # How many pax were disconnected from the largest network component post-disruption?
    non_largest_nodes = set(G.nodes()) - largest_cc_nodes 

    stranded_travelers = sum(
        0 if pd.isna(v := G.nodes[n].get("MorningDemand" if morning_demand else "TravelersPerDay")) else v
        for n in non_largest_nodes
    )

    if non_largest_nodes == set():
        non_largest_nodes = None
    
    if return_only_subgraph == False:
        return largest_sg, stranded_travelers, n_components, n_nodes_largest, non_largest_nodes
    else:
        return largest_sg

def _spearman_statistic(x, y):
    """Statistic function required by permutation_test."""
    try:
        result = stats.spearmanr(x, y).statistic
    except:
        result = None

    return result

def _vectorized_spearman(x, y, axis=-1):
    """
    Batched Spearman correlation for permutation_test(vectorized=True): 
    rank both samples along the resample axis, then take the Pearson correlation of the ranks.
    """
    x = stats.rankdata(x, axis=axis)
    y = stats.rankdata(y, axis=axis)
    xm = x - x.mean(axis=axis, keepdims=True)
    ym = y - y.mean(axis=axis, keepdims=True)
    num = (xm * ym).sum(axis=axis)
    den = np.sqrt((xm * xm).sum(axis=axis) * (ym * ym).sum(axis=axis))
    return num / den

def _get_measure_value(measure: dict, key):
    """Look up edge key, falling back to reversed direction if not found."""
    if key in measure:
        return measure[key]
    if isinstance(key, tuple) and len(key) == 2:
        reversed_key = (key[1], key[0])
        if reversed_key in measure:
            return measure[reversed_key]
    raise KeyError(f"Edge {key} not found in measure in either direction.")

def correlation_calc(metrics: pd.DataFrame, measures: dict[str, dict], filename: str, run_correlation: bool = True) -> pd.DataFrame:
    """
    Ranks disrupted edge metrics and measures, then calculates Spearman 
    correlation and permutation-based p-value for every (metric, measure) pair.
    Args:
        metrics:                  Raw output of disrupt_edges - index = (source, target), cols = metrics
        measures:                 Dict of {measure_name: {edge: value}}
        higher_is_more_important: Ranking direction for both metrics and measures
    Returns:
        DataFrame with rows = metrics, columns = measures, cells = (corr, pval)
    """
    if run_correlation:
        print(f"Running correlations for {filename}")
        # Rank metrics - drop default row, rank each column from metrics df 
        try:
            metrics = metrics.drop(('default','default'), axis=0)
            passed_type = 'edge'
        except KeyError:
            # node/block output keys its default row 'default'
            metrics = metrics.drop('default', axis=0)
            passed_type = 'node'
            # Dicts/lists cannot be ranked - drop these
            metrics = metrics.drop(columns=[
                'tt_default_dict', 'tt_alt_dict', 'tt_ipv_dict', 'tt_ov_dict',
                'disrupted_pax_flow_dict', 'disrupted_pax_min_flow_dict',
                'ipv_capacity_dict', 'ov_capacity_dict',
                'ic_boundary_nodes', 'block_nodes',
            ], errors='ignore')
        # The lower these values are the more impactful the disruption was
        lower_is_more_impactful = {
            "GE_u",
            "largest_component_size",
            "RSGC",
            "avg_degree",
            "degree_diversity",
            "avg_cluster_coef",
            "natural_connectivity",
            "algebraic_connectivity",
            "conductance",
            'n_nodes',
            'delta_ipv_capacity',
            'delta_ov_capacity',
            'delta_alt_capacity',
            'GE',
            }
        ranked_metrics = pd.DataFrame({
            col: sf.rank_elements(metrics[col], col in lower_is_more_impactful) # rank is in ascending order if true, else false -> max(value) = rank 1
            for col in metrics.columns
        })

        # Rank measures
        ranked_measures = {
            name: (
                pd.DataFrame.from_dict(measure, orient="index", columns=[name])
                .rank(method="min", na_option="keep", ascending=False) # All measures have the highest value = most important -> rank 1
                .to_dict()[name]
            )
            for name, measure in measures.items()
        }

        result = pd.DataFrame(index=ranked_metrics.columns, columns=ranked_measures.keys())

        num_metrics = ranked_metrics.shape[1]
        current_metric = 0
        for metric_name in ranked_metrics.columns:
            # Escape loop for non-metrics
            if metric_name in ('source','target','graph_connected','disconnected_nodes'):
                print(f"skipping {metric_name}")
                continue

            metric = ranked_metrics[metric_name].dropna().to_dict()

            current_metric = current_metric + 1
            print(f'Correlating metric {current_metric} out of {ranked_metrics.shape[1]}')
            for measure_name, measure in ranked_measures.items():
                shared_keys = sorted(
                    k for k in metric
                    if k in measure or (isinstance(k, tuple) and (k[1], k[0]) in measure)
                )

                # Permutation_test requires at least 2 observations per sample
                # A metric that's only defined (non-NaN) for 0 or 1 of the shared keys pointless to correlate
                if len(shared_keys) < 2:
                    if not shared_keys:
                        print(f"Warning: skipping ({metric_name}, {measure_name}) — no shared keys.")
                    else:
                        print(f"Warning: skipping ({metric_name}, {measure_name}) — only 1 shared key, not enough for a correlation.")
                    result.loc[metric_name, measure_name] = (None, None)
                    continue

                print(f'testing ',metric_name,' against ',measure_name,' for ',filename)
                metric_vals  = np.array([metric[k] for k in shared_keys])
                measure_vals = np.array([_get_measure_value(measure, k) for k in shared_keys])

                corr = _spearman_statistic(metric_vals, measure_vals)
                if np.isnan(metric_vals).any() or np.isnan(measure_vals).any():
                    # NaN samples
                    perm_result = stats.permutation_test(
                        data=(metric_vals, measure_vals),
                        statistic=lambda x, y: _spearman_statistic(x, y),
                        permutation_type="pairings",
                        n_resamples=9999,
                        alternative="two-sided",
                        random_state=42
                    )
                else:
                    perm_result = stats.permutation_test(
                        data=(metric_vals, measure_vals),
                        statistic=_vectorized_spearman,
                        vectorized=True,
                        permutation_type="pairings",
                        n_resamples=9999,
                        alternative="two-sided",
                        random_state=42
                    )
                result.loc[metric_name, measure_name] = (corr, perm_result.pvalue)

        result.to_json(sf.get_dir(f'export/{filename}.json'), orient='columns')
    else:
        with open(sf.get_dir(f'export/{filename}.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
        result = pd.DataFrame(data)
        result = result.map(
            lambda x: tuple(x) if isinstance(x, list) else x
        )
        print(f"Loaded correlation data for {filename}")

    return result

def disrupt_edges(G_services:nx.Graph, G_tracks: nx.Graph, G_ipv: nx.Graph, G_ov: nx.Graph, run_exp:bool=False, morning_demand:bool=True, disrupt_services:bool = True) -> pd.DataFrame:
    """
    Disrupts track edges one-by-one.

    Computes at the same time the metrics for:
        - the disrupted track graph with no bus replacements considered,
        - the track graph when bus replacements are considered (ipv or ov),
        - the service graph when bus replacements are considered (ipv or ov),
    """

    # Do I want to run the disruption procedure or load the last run?
    if run_exp:
        start_time = time.time()
        print(f"Edge disruptions started at: {time.strftime('%H:%M:%S')}")
        track_edges = [(u,v,e) for u,v,e in G_tracks.edges(data=True)]
        
        # Initialize output rows with default metrics
        result_tracks_no_alternative = {}
        result_tracks_ipv_alternative = {}
        result_tracks_ov_alternative = {}

        result_services_no_alternative = {}
        result_services_ipv_alternative = {}
        result_services_ov_alternative = {}

        # Track initialization - copy since all the same 
        default_track_metrics = metrics.edge_metrics(G_tracks)
        result_tracks_ipv_alternative[('default','default')] = dict(default_track_metrics)
        result_tracks_ov_alternative[('default','default')]  = dict(default_track_metrics)
        result_tracks_no_alternative[('default','default')]  = dict(default_track_metrics)

        # Service initialization
        default_service_metrics = metrics.edge_metrics(G_services)
        result_services_no_alternative[('default','default')]  = dict(default_service_metrics)
        result_services_ipv_alternative[('default','default')] = dict(default_service_metrics)
        result_services_ov_alternative[('default','default')]  = dict(default_service_metrics)

        # Default size
        default_n_nodes = G_tracks.number_of_nodes()
        default_n_edges = G_tracks.number_of_edges()

        # IPV speed alternatives for missing edges
        median_speed = np.nanmedian(list(nx.get_edge_attributes(G_tracks,"speed").values()))

        # Precompute each service edge's underlying track-edge sequence once
        default_n_nodes_services = G_services.number_of_nodes()
        service_edge_sequences = [
            (src, dst, set(zip(data.get('track_nodes', []), data.get('track_nodes', [])[1:])))
            for src, dst, data in G_services.edges(data=True)
        ]

        # Disruption loop
        i = 0
        t = 0
        for edge in track_edges:
            i += 1
            source, target = edge[0], edge[1]
            # Escape if either node is opstel
            if G_tracks.nodes[source].get("Type") in ("yard") or G_tracks.nodes[target].get("Type") in ("yard"):
                print(f"escaping track disruption loop because {source} or {target} is a yard")
                continue

            # Get default values for this edge
            tt_default = G_tracks[source][target]['travel_time']
            tt_ipv = None
            tt_ov = None
            

            ##### INFRA EDGES #####
            # Create the graph copies for each disruption scenario
            G_ipv_alternative   = G_tracks.copy() # The graph where travel times are adjusted
            G_ov_alternative    = G_tracks.copy() # The graph where ov alternatives are used
            G_disrupted         = G_tracks.copy() # The graph from which elements are removed

            # Remove the edge
            G_disrupted.remove_edge(source, target)
            # Try to find a path along the disrupted graph where no alternatives are offered
            try:
                tt_alt = nx.shortest_path_length(G_disrupted, source=source, target=target, weight='travel_time')
            except nx.NetworkXNoPath:
                tt_alt = None
            except nx.NodeNotFound:
                tt_alt = None

            # Get the largest subgraph + other statistics about this disruption scenario
            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disrupted, morning_demand=morning_demand)
            graph_connected = (n_components == 1)

            # Initialize the output for the non-replacement situation / has to be subgraph else metric calculation fails.
            result_tracks_no_alternative[(source,target)] = metrics.edge_metrics(G_subgraph, source=source, target=target)

            # Unique per-scenario override for no_alternative
            result_tracks_no_alternative[(source,target)].update({
                'n_nodes'                 : n_nodes,
                'graph_connected'         : graph_connected,
                'n_components'            : n_components,
                'disconnected_nodes'      : disconnected_nodes,
                'disconnected_travellers' : disconnected_travellers,
                'RSGC'                    : round(n_nodes / default_n_nodes,3),
            })

            disrupted_pax_flow     = round(G_tracks[source][target]['flow'], 0)
            disrupted_pax_min_flow = round(G_tracks[source][target]['pax_min'],0)

            # IPV alternative
            ipv_capacity = 0
            if G_services.has_edge(source, target) or G_services.has_edge(target, source):  # Check both orientations before indexing
                ipv_capacity = G_services[source][target]['capacity']
                if pd.isna(ipv_capacity):
                    ipv_capacity = 0
            delta_ipv_capacity = ipv_capacity - disrupted_pax_flow

            # Assign travel time to edge from ipv edge if exists
            if G_ipv.has_edge(source, target) or G_ipv.has_edge(target, source):  # Check both orientations before indexing
                tt_ipv = G_ipv[source][target]['ipv_travel_time'] if G_ipv.has_edge(source, target) else G_ipv[target][source]['ipv_travel_time']

            else:
                # If no edge exists fit travel time from median speed and length of track segment
                tt_ipv = median_speed * G_tracks[source][target]['geo_length']
                t += 1

            # Assign new travel times to track graph edge
            G_ipv_alternative[source][target]['travel_time'] = tt_ipv
            G_ipv_alternative[source][target]['pax_min'] = tt_ipv * G_ipv_alternative[source][target]['flow']

            # No need for subgraph because graph will always be connected (no edges removed, only retimed)
            result_tracks_ipv_alternative[(source,target)] = metrics.edge_metrics(G_ipv_alternative, source=source, target=target)
            result_tracks_ipv_alternative[(source,target)].update({
                'RSGC' : round(G_ipv_alternative.number_of_nodes() / default_n_nodes, 3),
            })

            ##### OV Alternative #####
            ov_capacity = None
            if G_services.has_edge(source, target) or G_services.has_edge(target, source):  # Check both orientations before indexing
                ov_capacity = G_services[source][target]['ov_capacity'] if G_services.has_edge(source, target) else G_services[target][source]['ov_capacity']
            if pd.isna(ov_capacity):
                ov_capacity = 0
            delta_ov_capacity = ov_capacity - disrupted_pax_flow

            if G_ov.has_edge(source, target) or G_ov.has_edge(target,source):
                tt_ov = G_ov[source][target]['travel_time_ov_min'] if G_ov.has_edge(source, target) else G_ov[target][source]['travel_time_ov_min'] #probably unnecessary because undirected
                G_ov_alternative[source][target]['travel_time'] = tt_ov
                G_ov_alternative[source][target]['pax_min'] = tt_ov * G_ov_alternative[source][target]['flow']
            # If no ov edge exists then do not fit some value, the graph is simply disconnected
            else:
                G_ov_alternative.remove_edge(source,target)
                tt_ov = None

            # Get subgraph for OV-only scenario since graph can be disconnected
            G_ov_subgraph, ov_disconnected_travellers, ov_n_components, ov_n_nodes, ov_disconnected_nodes = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_tracks_ov_alternative[(source,target)] = metrics.edge_metrics(G_ov_subgraph, source=source, target=target)
            result_tracks_ov_alternative[(source,target)].update({
                'n_nodes'                 : ov_n_nodes,
                'graph_connected'         : ov_n_components == 1,
                'n_components'            : ov_n_components,
                'disconnected_nodes'      : ov_disconnected_nodes,
                'disconnected_travellers' : ov_disconnected_travellers,
                'RSGC'                    : round(ov_n_nodes / default_n_nodes, 3),
            })

            # Metrics describing the disruption itself (travel times, passengers, capacity) 
            # Same for all scenarios
            shared_track_data = {
                'tt_default'             : tt_default,
                'tt_alt'                 : tt_alt,
                'tt_ipv'                 : tt_ipv,
                'tt_ov'                  : tt_ov,
                'disrupted_pax_flow'     : disrupted_pax_flow,
                'disrupted_pax_min_flow' : disrupted_pax_min_flow,
                'ipv_capacity'           : ipv_capacity,
                'delta_ipv_capacity'     : delta_ipv_capacity,
                'ov_capacity'            : ov_capacity,
                'delta_ov_capacity'      : delta_ov_capacity,
                'total_alt_capacity'     : ipv_capacity + ov_capacity,
                'delta_alt_capacity'     : (ipv_capacity + ov_capacity) - disrupted_pax_flow,
            }
            result_tracks_no_alternative[(source,target)].update(shared_track_data)
            result_tracks_ipv_alternative[(source,target)].update(shared_track_data)
            result_tracks_ov_alternative[(source,target)].update(shared_track_data)


            ##### SERVICE EDGES #####
            # Escape clause for if only want to look at track disruptions (no replacement scenario)
            if disrupt_services == False:
                continue

            # Escape clause for if a yard or aansluiting is being disrupted
            if G_tracks.nodes[source].get("Type") in ("connection","closed") or G_tracks.nodes[target].get("Type") in ("connection","closed"):
                print(f"Disrupted {i}/{default_n_edges} track edges | Current edge: {source} - {target}")
                print(f"Escaped service disruption iteration due to an edge involving a connection / closed type.")
                continue

            G_ipv_alternative = G_services.copy()  # Travel time adjusted graph (IPV)
            G_ov_alternative  = G_services.copy()
            G_disruption      = G_services.copy()  # Edge removed graph

            # Remove direct service edge if it exists
            if G_disruption.has_edge(source, target):
                G_disruption.remove_edge(source, target)

            # Remove affected overlapping service edges
            affected_tracks = [
                (src, dst) for src, dst, edge_sequence in service_edge_sequences
                if (source, target) in edge_sequence or (target, source) in edge_sequence
            ]

            # Try to get shortest path length without any alternatives.
            try:
                tt_alt_services = nx.shortest_path_length(G_disruption, source=source, target=target, weight='travel_time')
            except nx.NetworkXNoPath:
                tt_alt_services = None
            except nx.NodeNotFound:
                tt_alt_services = None

            G_disruption.remove_edges_from(affected_tracks)
            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disruption, morning_demand=morning_demand)
            graph_connected = (n_components == 1)

            # Initialize outputs for all three scenarios on the no-alternative subgraph
            base_service_metrics = metrics.edge_metrics(G_subgraph, source=source, target=target)
            result_services_no_alternative[(source,target)]   = dict(base_service_metrics)
            result_services_ipv_alternative[(source, target)] = dict(base_service_metrics)
            result_services_ov_alternative[(source,target)]   = dict(base_service_metrics)

            # Unique per-scenario override for no_alternative
            result_services_no_alternative[(source,target)].update({
                'n_nodes'                 : n_nodes,
                'graph_connected'         : graph_connected,
                'n_components'            : n_components,
                'disconnected_nodes'      : disconnected_nodes,
                'disconnected_travellers' : disconnected_travellers,
                'RSGC'                    : round(n_nodes / default_n_nodes_services,3),
            })

            # Guard against service edges that don't exist but are real stations
            if not G_services.has_edge(source,target):
                print(f"escaping service loop, no edge exists between {source} and {target}")
                continue

            # Set the travel time along the copied service edge to be the ipv_tt
            tt_ipv_services = tt_ipv
            if tt_ipv_services is not None and G_ipv_alternative.has_edge(source, target):
                G_ipv_alternative[source][target]['travel_time'] = tt_ipv_services

            ipv_tt_affected = None
            # For all affected tracks check if there exists an IPV bridge for the overlapping segment
            for src, dst in affected_tracks:
                if G_ipv.has_edge(src, dst):
                    ipv_tt_affected = G_ipv[src][dst].get('ipv_travel_time')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected
                elif G_ipv.has_edge(dst, src):
                    ipv_tt_affected = G_ipv[dst][src].get('ipv_travel_time')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected

            if tt_ipv_services is None and ipv_tt_affected is not None:
                tt_ipv_services = ipv_tt_affected

            result_services_ipv_alternative[(source, target)] = metrics.edge_metrics(G_ipv_alternative, source=source, target=target)
            result_services_ipv_alternative[(source, target)].update({
                'RSGC' : round(G_ipv_alternative.number_of_nodes() / default_n_nodes_services, 3),
            })

            ### OV alternative
            tt_ov_services = tt_ov
            if G_ov.has_edge(source,target) or G_ov.has_edge(target,source):
                tt_ov_services = G_ov[source][target]['travel_time_ov_min'] if G_ov.has_edge(source, target) else G_ov[target][source]['travel_time_ov_min']
                G_ov_alternative[source][target]['travel_time'] = tt_ov_services
                G_ov_alternative[source][target]['pax_min'] = tt_ov_services * G_ov_alternative[source][target]['flow']
            else:
                G_ov_alternative.remove_edge(source,target)
                tt_ov_services = None

            # For all affected tracks check if there exists an OV bridge for the overlapping segment
            ov_tt_affected = None
            for src, dst in affected_tracks:
                if G_ov.has_edge(src, dst):
                    ov_tt_affected = G_ov[src][dst].get('travel_time_ov_min')
                    if ov_tt_affected is not None and G_ov_alternative.has_edge(src, dst):
                        G_ov_alternative[src][dst]['travel_time'] = ov_tt_affected
                        G_ov_alternative[src][dst]['pax_min'] = ov_tt_affected * G_ov_alternative[src][dst]['flow']
                elif G_ov.has_edge(dst, src):
                    ov_tt_affected = G_ov[dst][src].get('travel_time_ov_min')
                    if ov_tt_affected is not None and G_ov_alternative.has_edge(src, dst):
                        G_ov_alternative[src][dst]['travel_time'] = ov_tt_affected
                        G_ov_alternative[src][dst]['pax_min'] = ov_tt_affected * G_ov_alternative[src][dst]['flow']

            # Set printed value to whatever the last affected value was so not None while graph is connected via alt path
            if tt_ov_services is None and ov_tt_affected is not None:
                tt_ov_services = ov_tt_affected

            G_ov_subgraph_services, ov_disconnected_travellers_s, ov_n_components_s, ov_n_nodes_s, ov_disconnected_nodes_s = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_services_ov_alternative[(source,target)] = metrics.edge_metrics(G_ov_subgraph_services, source=source, target=target)
            result_services_ov_alternative[(source,target)].update({
                'n_nodes'                 : ov_n_nodes_s,
                'graph_connected'         : ov_n_components_s == 1,
                'n_components'            : ov_n_components_s,
                'disconnected_nodes'      : ov_disconnected_nodes_s,
                'disconnected_travellers' : ov_disconnected_travellers_s,
                'RSGC'                    : round(ov_n_nodes_s / default_n_nodes_services, 3),
            })

            # Metrics describing the disruption itself
            shared_service_data = {
                'tt_default'             : tt_default,
                'tt_alt'                 : tt_alt_services,
                'tt_ipv'                 : tt_ipv_services,
                'tt_ov'                  : tt_ov_services,
                'disrupted_pax_flow'     : disrupted_pax_flow,
                'disrupted_pax_min_flow' : disrupted_pax_min_flow,
                'ipv_capacity'           : ipv_capacity,
                'delta_ipv_capacity'     : delta_ipv_capacity,
                'ov_capacity'            : ov_capacity,
                'delta_ov_capacity'      : delta_ov_capacity,
                'total_alt_capacity'     : ipv_capacity + ov_capacity,
                'delta_alt_capacity'     : (ipv_capacity + ov_capacity) - disrupted_pax_flow,
            }

            result_services_no_alternative[(source,target)].update(shared_service_data)
            result_services_ov_alternative[(source,target)].update(shared_service_data)
            result_services_ipv_alternative[(source,target)].update(shared_service_data)

            print(f"Disrupted {i}/{default_n_edges} track edges | Current edge: {source} - {target}")

        print(f"Extrapolated {t} ipv travel times to track graph")

        def _dict_to_json(results:dict, filename:str) -> pd.DataFrame:
            # Takes the result dict and stores it as json based on dict name
            metric_df = pd.DataFrame.from_dict(results, orient='index')
            metric_df.index = pd.MultiIndex.from_tuples(metric_df.index, names=['source','target'])
            metric_df.to_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            return metric_df

        edge_metrics_tracks_no_alternative = _dict_to_json(result_tracks_no_alternative, filename='edge_disruption_data_tracks_no_alternative')
        edge_metrics_tracks_ipv_alt        = _dict_to_json(result_tracks_ipv_alternative, filename='edge_disruption_data_tracks_ipv_alt')
        edge_metrics_tracks_ov_alt         = _dict_to_json(result_tracks_ov_alternative, filename='edge_disruption_data_tracks_ov_alt')

        edge_metrics_services_no_alternative = _dict_to_json(result_services_no_alternative, filename='edge_disruption_data_services_no_alternative')
        edge_metrics_services_ipv_alt        = _dict_to_json(result_services_ipv_alternative, filename='edge_disruption_data_services_ipv_alt')
        edge_metrics_services_ov_alt         = _dict_to_json(result_services_ov_alternative, filename='edge_disruption_data_services_ov_alt')

        total_time = time.time() - start_time
        print(f"Edge disruptions finished at: {time.strftime('%H:%M:%S')}  (total: {total_time:.0f}s)")

    else:
        # Load prior run
        def _json_to_df(filename:str)->pd.DataFrame:
            # Takes the passed name and loads the json into a df
            df = pd.read_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            df.index = df.index.map(ast.literal_eval)

            return df

        edge_metrics_tracks_no_alternative = _json_to_df(filename='edge_disruption_data_tracks_no_alternative')
        edge_metrics_tracks_ipv_alt        = _json_to_df(filename='edge_disruption_data_tracks_ipv_alt')
        edge_metrics_tracks_ov_alt         = _json_to_df(filename='edge_disruption_data_tracks_ov_alt')

        edge_metrics_services_no_alternative = _json_to_df(filename='edge_disruption_data_services_no_alternative')
        edge_metrics_services_ipv_alt        = _json_to_df(filename='edge_disruption_data_services_ipv_alt')
        edge_metrics_services_ov_alt         = _json_to_df(filename='edge_disruption_data_services_ov_alt')        

        print("loaded edge disruptions")

    return edge_metrics_tracks_no_alternative, edge_metrics_tracks_ipv_alt, edge_metrics_tracks_ov_alt, edge_metrics_services_no_alternative, edge_metrics_services_ipv_alt, edge_metrics_services_ov_alt


def disrupt_blocks(G_services:nx.Graph, G_tracks: nx.Graph, G_ipv: nx.Graph, G_ov: nx.Graph, run_exp:bool=False, morning_demand:bool=True, disrupt_services:bool = True) -> pd.DataFrame:
    """
    Disrupts each block one-by-one.

    A block is a set of track nodes/edges between two or more block nodes.
    Everything sharing that block id is removed at once. 

    One disruption = 1 block (track set) removed

    Computes at the same time the metrics for:
        - the disrupted track graph with no bus replacements considered,
        - the track graph when bus replacements are considered (ipv or ov),
        - the service graph when bus replacements are considered (ipv or ov),
    """

    if run_exp:
        start_time = time.time()
        print(f"Block disruptions started at: {time.strftime('%H:%M:%S')}")

        # Group nodes/edges by block_id. If no nodes inside block get edge. 
        node_block_ids = nx.get_node_attributes(G_tracks, 'block_id')
        edge_block_ids = nx.get_edge_attributes(G_tracks, 'block_id')

        block_nodes = defaultdict(set)
        for node, block_id in node_block_ids.items():
            block_nodes[block_id].add(node)

        block_edges = defaultdict(set)
        for edge, block_id in edge_block_ids.items():
            block_edges[block_id].add(edge)

        block_ids = sorted(set(block_nodes) | set(block_edges))
        no_blocks = len(block_ids)

        # Initialize output rows with default metrics
        result_tracks_no_alternative    = {}
        result_tracks_ipv_alternative   = {}
        result_tracks_ov_alternative    = {}
        result_services_no_alternative  = {}
        result_services_ipv_alternative = {}
        result_services_ov_alternative  = {}

        # Identical undisrupted baselines - compute once per graph, one copy per scenario
        default_track_metrics   = metrics.node_metrics(G_tracks)
        default_service_metrics = metrics.node_metrics(G_services)
        result_tracks_no_alternative['default']    = dict(default_track_metrics)
        result_tracks_ipv_alternative['default']   = dict(default_track_metrics)
        result_tracks_ov_alternative['default']    = dict(default_track_metrics)
        result_services_no_alternative['default']  = dict(default_service_metrics)
        result_services_ipv_alternative['default'] = dict(default_service_metrics)
        result_services_ov_alternative['default']  = dict(default_service_metrics)

        # Default size
        default_n_nodes = G_tracks.number_of_nodes()
        default_n_nodes_services = G_services.number_of_nodes()

        # IPV speed alternative for missing edges
        median_speed = np.nanmedian(list(nx.get_edge_attributes(G_tracks, "speed").values()))

        # Precompute each service edge's underlying track path
        service_edge_paths = [
            (src, dst, set(data.get('track_nodes', [])), set(zip(data.get('track_nodes', []), data.get('track_nodes', [])[1:])))
            for src, dst, data in G_services.edges(data=True)
        ]

        # Disruption loop
        i = 0
        for block_id in block_ids:
            i += 1
            nodes_in_block = block_nodes.get(block_id, set())
            edges_in_block = block_edges.get(block_id, set())
            edges_in_block_bidir = edges_in_block | {(v, u) for u, v in edges_in_block}

            # Boundary IC stations: endpoints of the block's tagged edges that aren't themselves
            # part of the block (a block can be bounded by more than 2 IC stations once segments
            # get merged by dp.create_blocks).
            ic_boundary_nodes = sorted({
                n for u, v in edges_in_block for n in (u, v) if n not in nodes_in_block
            })

            if len(ic_boundary_nodes) < 2:
                print(f"escaping block disruption loop for block {block_id}: fewer than 2 boundary IC stations found")
                continue

            ic_pairs = list(itertools.combinations(ic_boundary_nodes, 2))

            ##### INFRA BLOCK #####
            G_ipv_alternative = G_tracks.copy()  # The graph where travel times are adjusted
            G_ov_alternative  = G_tracks.copy()  # The graph where ov alternatives are used
            G_disrupted       = G_tracks.copy()  # The graph from which elements are removed

            # Remove the block
            G_disrupted.remove_nodes_from(nodes_in_block)
            G_disrupted.remove_edges_from(edges_in_block)

            # Alternative travel time between every pair of boundary IC stations, both undisrupted and disrupted
            tt_default_dict = {}
            tt_alt_dict     = {}
            for a, b in ic_pairs:
                try:
                    tt_default_dict[(a, b)] = nx.shortest_path_length(G_tracks, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_default_dict[(a, b)] = np.nan
                try:
                    tt_alt_dict[(a, b)] = nx.shortest_path_length(G_disrupted, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_alt_dict[(a, b)] = np.nan

            
            tt_default_values_tracks = list(tt_default_dict.values())
            tt_default_avg_tracks = np.nanmean(tt_default_values_tracks) if tt_default_values_tracks and not np.all(np.isnan(tt_default_values_tracks)) else np.nan
            tt_default_sum_tracks = np.nansum(tt_default_values_tracks) if tt_default_values_tracks and not np.all(np.isnan(tt_default_values_tracks)) else np.nan

            tt_alt_values = list(tt_alt_dict.values())
            tt_alt_avg = np.nanmean(tt_alt_values) if tt_alt_values and not np.all(np.isnan(tt_alt_values)) else np.nan
            tt_alt_sum = np.nansum(tt_alt_values) if tt_alt_values and not np.all(np.isnan(tt_alt_values)) else np.nan

            # Passengers physically located inside the disrupted block
            disconnected_passengers = sum(
                0 if pd.isna(v := G_tracks.nodes[n].get("MorningDemand" if morning_demand else "TravelersPerDay")) else v
                for n in nodes_in_block
            )

            # Get the largest subgraph + other statistics about this disruption scenario
            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disrupted, morning_demand=morning_demand)
            graph_connected = (n_components == 1)

            # Only the no_alternative row is metric'd on G_subgraph
            result_tracks_no_alternative[block_id] = metrics.node_metrics(G_subgraph, node=block_id)

            # Unique per-scenario override for no_alternative
            result_tracks_no_alternative[block_id].update({
                'n_nodes'                 : n_nodes,
                'graph_connected'         : graph_connected,
                'n_components'            : n_components,
                'disconnected_nodes'      : disconnected_nodes,
                'disconnected_travellers' : disconnected_travellers,
                'RSGC'                    : round(n_nodes / default_n_nodes, 3),
            })

            disrupted_pax_flow_dict     = {(u, v): round(G_tracks[u][v]['flow'], 0)    for u, v in edges_in_block}
            disrupted_pax_min_flow_dict = {(u, v): round(G_tracks[u][v]['pax_min'], 0) for u, v in edges_in_block}
            disrupted_pax_flow_sum      = round(np.sum(list(disrupted_pax_flow_dict.values())))
            disrupted_pax_min_flow_sum  = round(np.sum(list(disrupted_pax_min_flow_dict.values())))

            # IPV alternative
            ipv_capacity_dict = {}
            for u, v in edges_in_block:
                if G_services.has_edge(u, v):
                    cap = G_services[u][v]['capacity']
                else:
                    cap = np.nan
                ipv_capacity_dict[(u, v)] = 0 if pd.isna(cap) else cap
            ipv_capacity_sum = round(np.sum(list(ipv_capacity_dict.values())))
            delta_ipv_capacity_sum = ipv_capacity_sum - disrupted_pax_flow_sum

            # Retime every edge in the block using real G_ipv data where it exists, falling back to meidan speed
            for u, v in edges_in_block:
                if G_ipv.has_edge(u, v) or G_ipv.has_edge(v, u):
                    tt_ipv = G_ipv[u][v]['ipv_travel_time'] if G_ipv.has_edge(u, v) else G_ipv[v][u]['ipv_travel_time']
                else:
                    tt_ipv = median_speed * G_tracks[u][v]['geo_length']
                if G_ipv_alternative.has_edge(u, v):
                    G_ipv_alternative[u][v]['travel_time'] = tt_ipv
                    G_ipv_alternative[u][v]['pax_min'] = tt_ipv * G_ipv_alternative[u][v]['flow']

            result_tracks_ipv_alternative[block_id] = metrics.node_metrics(G_ipv_alternative, node=block_id)
            result_tracks_ipv_alternative[block_id].update({
                'RSGC' : round(G_ipv_alternative.number_of_nodes() / default_n_nodes, 3),
            })

            tt_ipv_dict = {}
            for a, b in ic_pairs:
                try:
                    tt_ipv_dict[(a, b)] = nx.shortest_path_length(G_ipv_alternative, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_ipv_dict[(a, b)] = np.nan

            tt_ipv_values = list(tt_ipv_dict.values())
            tt_ipv_avg = np.nanmean(tt_ipv_values) if tt_ipv_values and not np.all(np.isnan(tt_ipv_values)) else np.nan
            tt_ipv_sum = np.nansum(tt_ipv_values) if tt_ipv_values and not np.all(np.isnan(tt_ipv_values)) else np.nan


            ##### OV Alternative #####
            ov_capacity_dict = {}
            for u, v in edges_in_block:
                if G_services.has_edge(u, v):
                    cap = G_services[u][v]['ov_capacity']
                else:
                    cap = np.nan
                ov_capacity_dict[(u, v)] = 0 if pd.isna(cap) else cap
            ov_capacity_sum = round(np.sum(list(ov_capacity_dict.values())))
            delta_ov_capacity_sum = ov_capacity_sum - disrupted_pax_flow_sum

            # An edge only stays in G_ov_alternative if a real OV bridge exists for it
            for u, v in edges_in_block:
                if G_ov.has_edge(u, v) or G_ov.has_edge(v, u):
                    tt_ov = G_ov[u][v]['travel_time_ov_min'] if G_ov.has_edge(u, v) else G_ov[v][u]['travel_time_ov_min']
                    if G_ov_alternative.has_edge(u, v):
                        G_ov_alternative[u][v]['travel_time'] = tt_ov
                        G_ov_alternative[u][v]['pax_min'] = tt_ov * G_ov_alternative[u][v]['flow']
                elif G_ov_alternative.has_edge(u, v):
                    G_ov_alternative.remove_edge(u, v)

            G_ov_subgraph, ov_disconnected_travellers, ov_n_components, ov_n_nodes, ov_disconnected_nodes = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_tracks_ov_alternative[block_id] = metrics.node_metrics(G_ov_subgraph, node=block_id)
            result_tracks_ov_alternative[block_id].update({
                'n_nodes'                 : ov_n_nodes,
                'graph_connected'         : ov_n_components == 1,
                'n_components'            : ov_n_components,
                'disconnected_nodes'      : ov_disconnected_nodes,
                'disconnected_travellers' : ov_disconnected_travellers,
                'RSGC'                    : round(ov_n_nodes / default_n_nodes, 3),
            })

            tt_ov_dict = {}
            for a, b in ic_pairs:
                try:
                    tt_ov_dict[(a, b)] = nx.shortest_path_length(G_ov_alternative, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_ov_dict[(a, b)] = np.nan

            tt_ov_values = list(tt_ov_dict.values())
            tt_ov_avg = np.nanmean(tt_ov_values) if tt_ov_values and not np.all(np.isnan(tt_ov_values)) else np.nan
            tt_ov_sum = np.nansum(tt_ov_values) if tt_ov_values and not np.all(np.isnan(tt_ov_values)) else np.nan

            # Metrics describing the disruption itself
            shared_track_data = {
                'ic_boundary_nodes'           : ic_boundary_nodes,
                'block_nodes'                 : sorted(nodes_in_block),
                'tt_default_dict'             : tt_default_dict,
                'tt_alt_dict'                 : tt_alt_dict,
                'tt_alt_avg'                  : tt_alt_avg,
                'tt_alt_sum'                  : tt_alt_sum,
                'tt_ipv_dict'                 : tt_ipv_dict,
                'tt_ipv_avg'                  : tt_ipv_avg,
                'tt_ipv_sum'                  : tt_ipv_sum,
                'tt_ov_dict'                  : tt_ov_dict,
                'tt_ov_avg'                   : tt_ov_avg,
                'tt_ov_sum'                   : tt_ov_sum,
                'disconnected_passengers'     : disconnected_passengers,
                'disrupted_pax_flow_dict'     : disrupted_pax_flow_dict,
                'disrupted_pax_flow_sum'      : disrupted_pax_flow_sum,
                'disrupted_pax_min_flow_dict' : disrupted_pax_min_flow_dict,
                'disrupted_pax_min_flow_sum'  : disrupted_pax_min_flow_sum,
                'ipv_capacity_dict'           : ipv_capacity_dict,
                'ipv_capacity_sum'            : ipv_capacity_sum,
                'delta_ipv_capacity_sum'      : delta_ipv_capacity_sum,
                'ov_capacity_dict'            : ov_capacity_dict,
                'ov_capacity_sum'             : ov_capacity_sum,
                'delta_ov_capacity_sum'       : delta_ov_capacity_sum,
                'total_alt_capacity'          : ipv_capacity_sum + ov_capacity_sum,
                'delta_alt_capacity'          : (ipv_capacity_sum + ov_capacity_sum) - disrupted_pax_flow_sum,
            }
            result_tracks_no_alternative[block_id].update(shared_track_data)
            result_tracks_ipv_alternative[block_id].update(shared_track_data)
            result_tracks_ov_alternative[block_id].update(shared_track_data)


            ##### SERVICE BLOCK #####
            # Escape clause for if only want to look at track disruptions (no replacement scenario)
            if disrupt_services == False:
                continue

            # Escape clause if the boundary stations aren't all real service stops (ghost stations) 
            if not all(G_services.has_node(n) for n in ic_boundary_nodes):
                print(f"escaping service block disruption for block {block_id}: not all boundary stations exist in the service graph")
                continue

            G_ipv_alternative = G_services.copy()  # Travel time adjusted graph (IPV)
            G_ov_alternative  = G_services.copy()
            G_disruption      = G_services.copy()  # Node/edge removed graph

            # Remove any of the block's own nodes that are real service stops
            G_disruption.remove_nodes_from(nodes_in_block & set(G_services.nodes()))

            # Remove affected overlapping service edges based on precalculated track paths 
            affected_service_edges = [
                (src, dst) for src, dst, path_nodes, edge_sequence in service_edge_paths
                if (nodes_in_block & path_nodes) or (edges_in_block_bidir & edge_sequence)
            ]

            G_disruption.remove_edges_from(affected_service_edges)

            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disruption, morning_demand=morning_demand)
            graph_connected = (n_components == 1)

            # Only the no_alternative row is metric'd on G_subgraph
            result_services_no_alternative[block_id] = metrics.node_metrics(G_subgraph, node=block_id)

            # Unique per-scenario override for no_alternative
            result_services_no_alternative[block_id].update({
                'n_nodes'                 : n_nodes,
                'graph_connected'         : graph_connected,
                'n_components'            : n_components,
                'disconnected_nodes'      : disconnected_nodes,
                'disconnected_travellers' : disconnected_travellers,
                'RSGC'                    : round(n_nodes / default_n_nodes_services, 3),
            })

            # tt_default/tt_alt between the boundary IC stations, calculated on the service graph
            tt_default_dict_services = {}
            tt_alt_dict_services     = {}
            for a, b in ic_pairs:
                try:
                    tt_default_dict_services[(a, b)] = nx.shortest_path_length(G_services, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_default_dict_services[(a, b)] = np.nan
                try:
                    tt_alt_dict_services[(a, b)] = nx.shortest_path_length(G_disruption, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_alt_dict_services[(a, b)] = np.nan

            tt_default_values_services = list(tt_default_dict_services.values())
            tt_default_avg_services = np.nanmean(tt_default_values_services) if tt_default_values_services and not np.all(np.isnan(tt_default_values_services)) else np.nan
            tt_default_sum_services = np.nansum(tt_default_values_services) if tt_default_values_services and not np.all(np.isnan(tt_default_values_services)) else np.nan

            tt_alt_values_services = list(tt_alt_dict_services.values())
            tt_alt_avg_services = np.nanmean(tt_alt_values_services) if tt_alt_values_services and not np.all(np.isnan(tt_alt_values_services)) else np.nan
            tt_alt_sum_services = np.nansum(tt_alt_values_services) if tt_alt_values_services and not np.all(np.isnan(tt_alt_values_services)) else np.nan

            # IPV alternative
            for src, dst in affected_service_edges:
                if G_ipv.has_edge(src, dst):
                    ipv_tt_affected = G_ipv[src][dst].get('ipv_travel_time')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected
                elif G_ipv.has_edge(dst, src):
                    ipv_tt_affected = G_ipv[dst][src].get('ipv_travel_time')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected

            result_services_ipv_alternative[block_id] = metrics.node_metrics(G_ipv_alternative, node=block_id)
            result_services_ipv_alternative[block_id].update({
                'RSGC' : round(G_ipv_alternative.number_of_nodes() / default_n_nodes_services, 3),
            })

            tt_ipv_dict_services = {}
            for a, b in ic_pairs:
                try:
                    tt_ipv_dict_services[(a, b)] = nx.shortest_path_length(G_ipv_alternative, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_ipv_dict_services[(a, b)] = np.nan

            tt_ipv_values_services = list(tt_ipv_dict_services.values())
            tt_ipv_avg_services = np.nanmean(tt_ipv_values_services) if tt_ipv_values_services and not np.all(np.isnan(tt_ipv_values_services)) else np.nan
            tt_ipv_sum_services = np.nansum(tt_ipv_values_services) if tt_ipv_values_services and not np.all(np.isnan(tt_ipv_values_services)) else np.nan

            # OV alternative
            for src, dst in affected_service_edges:
                if G_ov.has_edge(src, dst) or G_ov.has_edge(dst, src):
                    ov_tt_affected = G_ov[src][dst]['travel_time_ov_min'] if G_ov.has_edge(src, dst) else G_ov[dst][src]['travel_time_ov_min']
                    if G_ov_alternative.has_edge(src, dst):
                        G_ov_alternative[src][dst]['travel_time'] = ov_tt_affected
                        G_ov_alternative[src][dst]['pax_min'] = ov_tt_affected * G_ov_alternative[src][dst]['flow']
                elif G_ov_alternative.has_edge(src, dst):
                    G_ov_alternative.remove_edge(src, dst)

            G_ov_subgraph_services, ov_disconnected_travellers_s, ov_n_components_s, ov_n_nodes_s, ov_disconnected_nodes_s = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_services_ov_alternative[block_id] = metrics.node_metrics(G_ov_subgraph_services, node=block_id)
            result_services_ov_alternative[block_id].update({
                'n_nodes'                 : ov_n_nodes_s,
                'graph_connected'         : ov_n_components_s == 1,
                'n_components'            : ov_n_components_s,
                'disconnected_nodes'      : ov_disconnected_nodes_s,
                'disconnected_travellers' : ov_disconnected_travellers_s,
                'RSGC'                    : round(ov_n_nodes_s / default_n_nodes_services, 3),
            })

            tt_ov_dict_services = {}
            for a, b in ic_pairs:
                try:
                    tt_ov_dict_services[(a, b)] = nx.shortest_path_length(G_ov_alternative, source=a, target=b, weight='travel_time')
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    tt_ov_dict_services[(a, b)] = np.nan

            tt_ov_values_services = list(tt_ov_dict_services.values())
            tt_ov_avg_services = np.nanmean(tt_ov_values_services) if tt_ov_values_services and not np.all(np.isnan(tt_ov_values_services)) else np.nan
            tt_ov_sum_services = np.nansum(tt_ov_values_services) if tt_ov_values_services and not np.all(np.isnan(tt_ov_values_services)) else np.nan

            # Metrics describing the disruption itself
            shared_service_data = {
                'ic_boundary_nodes'           : ic_boundary_nodes,
                'block_nodes'                 : sorted(nodes_in_block),
                'tt_default_dict'             : tt_default_dict_services,
                'tt_default_avg'              : tt_default_avg_services,
                'tt_default_sum'              : tt_default_sum_services,
                'tt_alt_dict'                 : tt_alt_dict_services,
                'tt_alt_avg'                  : tt_alt_avg_services,
                'tt_alt_sum'                  : tt_alt_sum_services,
                'tt_ipv_dict'                 : tt_ipv_dict_services,
                'tt_ipv_avg'                  : tt_ipv_avg_services,
                'tt_ipv_sum'                  : tt_ipv_sum_services,
                'tt_ov_dict'                  : tt_ov_dict_services,
                'tt_ov_avg'                   : tt_ov_avg_services,
                'tt_ov_sum'                   : tt_ov_sum_services,
                'disconnected_passengers'     : disconnected_passengers,
                'disrupted_pax_flow_dict'     : disrupted_pax_flow_dict,
                'disrupted_pax_flow_sum'      : disrupted_pax_flow_sum,
                'disrupted_pax_min_flow_dict' : disrupted_pax_min_flow_dict,
                'disrupted_pax_min_flow_sum'  : disrupted_pax_min_flow_sum,
                'ipv_capacity_dict'           : ipv_capacity_dict,
                'ipv_capacity_sum'            : ipv_capacity_sum,
                'delta_ipv_capacity_sum'      : delta_ipv_capacity_sum,
                'ov_capacity_dict'            : ov_capacity_dict,
                'ov_capacity_sum'             : ov_capacity_sum,
                'delta_ov_capacity_sum'       : delta_ov_capacity_sum,
                'total_alt_capacity'          : ipv_capacity_sum + ov_capacity_sum,
                'delta_alt_capacity'          : (ipv_capacity_sum + ov_capacity_sum) - disrupted_pax_flow_sum,
            }
            result_services_no_alternative[block_id].update(shared_service_data)
            result_services_ipv_alternative[block_id].update(shared_service_data)
            result_services_ov_alternative[block_id].update(shared_service_data)

            print(f"Disrupted block {i}/{no_blocks} | block_id: {block_id} | boundary stations: {ic_boundary_nodes}")

        def _dict_to_json(results:dict, filename:str) -> pd.DataFrame:
            # Takes the result dict and stores it as json based on dict name
            metric_df = pd.DataFrame.from_dict(results, orient='index')
            metric_df.index.name = 'block_id'
            metric_df.to_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            return metric_df

        block_metrics_tracks_no_alternative = _dict_to_json(result_tracks_no_alternative, filename='block_disruption_data_tracks_no_alternative')
        block_metrics_tracks_ipv_alt        = _dict_to_json(result_tracks_ipv_alternative, filename='block_disruption_data_tracks_ipv_alt')
        block_metrics_tracks_ov_alt         = _dict_to_json(result_tracks_ov_alternative, filename='block_disruption_data_tracks_ov_alt')

        block_metrics_services_no_alternative = _dict_to_json(result_services_no_alternative, filename='block_disruption_data_services_no_alternative')
        block_metrics_services_ipv_alt        = _dict_to_json(result_services_ipv_alternative, filename='block_disruption_data_services_ipv_alt')
        block_metrics_services_ov_alt         = _dict_to_json(result_services_ov_alternative, filename='block_disruption_data_services_ov_alt')

        total_time = time.time() - start_time
        print(f"Block disruptions finished at: {time.strftime('%H:%M:%S')}  (total: {total_time:.0f}s)")

    else:
        # Load prior run
        def _json_to_df(filename:str)->pd.DataFrame:
            df = pd.read_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            df.index = df.index.map(lambda idx: int(idx) if idx != 'default' else idx) # infer as int
            return df

        block_metrics_tracks_no_alternative = _json_to_df(filename='block_disruption_data_tracks_no_alternative')
        block_metrics_tracks_ipv_alt        = _json_to_df(filename='block_disruption_data_tracks_ipv_alt')
        block_metrics_tracks_ov_alt         = _json_to_df(filename='block_disruption_data_tracks_ov_alt')

        block_metrics_services_no_alternative = _json_to_df(filename='block_disruption_data_services_no_alternative')
        block_metrics_services_ipv_alt        = _json_to_df(filename='block_disruption_data_services_ipv_alt')
        block_metrics_services_ov_alt         = _json_to_df(filename='block_disruption_data_services_ov_alt')

        print("loaded block disruptions")

    return block_metrics_tracks_no_alternative, block_metrics_tracks_ipv_alt, block_metrics_tracks_ov_alt, block_metrics_services_no_alternative, block_metrics_services_ipv_alt, block_metrics_services_ov_alt


def targeted_edge_disruption(G_tracks:nx.Graph, G_services:nx.Graph, G_ipv:nx.Graph, G_ov:nx.Graph, target1:str, target2:str, morning_demand:bool=True,scale_factor:float = 1.343732, decay:float = 1.8888):
    """
    Disrupt a single edge and calculate metrics on it
    """

    # Get default values for this edge
    tt_default = G_tracks[target1][target2]['travel_time']
    tt_ipv = None
    tt_ov = None
    default_n_nodes = G_tracks.number_of_nodes()

    ##### INFRA EDGES #####
    # Create the graph copies for each disruption scenario
    G_ipv_alternative   = G_tracks.copy() # The graph where travel times are adjusted
    G_ov_alternative    = G_tracks.copy() # The graph where ov alternatives are used
    G_disrupted         = G_tracks.copy() # The graph from which elements are removed

    # Remove the edge
    G_disrupted.remove_edge(target1, target2)
    # Try to find a path along the disrupted graph where no alternatives are offered
    try:
        tt_alt = nx.shortest_path_length(G_disrupted, source=target1, target=target2, weight='travel_time')
    except nx.NetworkXNoPath:
        tt_alt = None
    except nx.NodeNotFound:
        tt_alt = None

    # Get the largest subgraph + other statistics about this disruption scenario
    G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disrupted, morning_demand=morning_demand)
    graph_connected = (n_components == 1)

    # Initialize the outputs for the non-replacement situation / has to be subgraph else metric calculation fails
    result_tracks_no_alternative  = metrics.edge_metrics(G_subgraph, source=target1, target=target2)
    result_tracks_ipv_alternative = metrics.edge_metrics(G_subgraph, source=target1, target=target2)
    result_tracks_ov_alternative  = metrics.edge_metrics(G_subgraph, source=target1, target=target2)

    # Unique per-scenario override for no_alternative
    result_tracks_no_alternative.update({
        'n_nodes'                 : n_nodes,
        'graph_connected'         : graph_connected,
        'n_components'            : n_components,
        'disconnected_nodes'      : disconnected_nodes,
        'disconnected_travellers' : disconnected_travellers,
        'RSGC'                    : round(n_nodes / default_n_nodes, 3),
    })

    disrupted_pax_flow     = round(G_tracks[target1][target2]['flow'], 0)
    disrupted_pax_min_flow = round(G_tracks[target1][target2]['pax_min'],0)

    # IPV alternative - guard orientation
    ipv_capacity = 0
    if G_services.has_edge(target1, target2) or G_services.has_edge(target2, target1):
        ipv_capacity = G_services[target1][target2]['capacity'] if G_services.has_edge(target1, target2) else G_services[target2][target1]['capacity']
        if pd.isna(ipv_capacity):
            ipv_capacity = 0
    delta_ipv_capacity = ipv_capacity - disrupted_pax_flow

    # Assign travel time to edge from ipv edge if exists
    if G_ipv.has_edge(target1, target2) or G_ipv.has_edge(target2, target1):  # Check both orientations before indexing
        tt_ipv = G_ipv[target1][target2]['ipv_travel_time'] if G_ipv.has_edge(target1, target2) else G_ipv[target2][target1]['ipv_travel_time']

    else:
        # If no edge exists fit travel time from median speed and length of track segment
        median_speed = np.nanmedian(list(nx.get_edge_attributes(G_tracks,"speed").values()))
        tt_ipv = median_speed * G_tracks[target1][target2]['geo_length']

    # Assign new travel times to track graph edge
    G_ipv_alternative[target1][target2]['travel_time'] = tt_ipv
    G_ipv_alternative[target1][target2]['pax_min'] = tt_ipv * G_ipv_alternative[target1][target2]['flow']

    # No need for subgraph because graph will always be connected (no edges removed, only retimed)
    result_tracks_ipv_alternative = metrics.edge_metrics(G_ipv_alternative, source=target1, target=target2)
    result_tracks_ipv_alternative.update({
        'RSGC' : round(G_ipv_alternative.number_of_nodes() / default_n_nodes, 3),
    })

    ##### OV Alternative #####
    ov_capacity = 0
    if G_services.has_edge(target1, target2) or G_services.has_edge(target2, target1):
        ov_capacity = G_services[target1][target2]['ov_capacity'] if G_services.has_edge(target1, target2) else G_services[target2][target1]['ov_capacity']
        if pd.isna(ov_capacity):
            ov_capacity = 0
    delta_ov_capacity = ov_capacity - disrupted_pax_flow

    if G_ov.has_edge(target1, target2) or G_ov.has_edge(target2,target1):
        tt_ov = G_ov[target1][target2]['travel_time_ov_min'] if G_ov.has_edge(target1, target2) else G_ov[target2][target1]['travel_time_ov_min'] #probably unnecessary because undirected
        G_ov_alternative[target1][target2]['travel_time'] = tt_ov
        G_ov_alternative[target1][target2]['pax_min'] = tt_ov * G_ov_alternative[target1][target2]['flow']
    # If no ov edge exists then do not fit some value, the graph is simply disconnected
    else:
        G_ov_alternative.remove_edge(target1,target2)
        tt_ov = None

    # Get subgraph for OV-only scenario since graph can be disconnected
    G_ov_subgraph, ov_disconnected_travellers, ov_n_components, ov_n_nodes, ov_disconnected_nodes = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
    result_tracks_ov_alternative = metrics.edge_metrics(G_ov_subgraph, source=target1, target=target2)
    result_tracks_ov_alternative.update({
        'n_nodes'                 : ov_n_nodes,
        'graph_connected'         : ov_n_components == 1,
        'n_components'            : ov_n_components,
        'disconnected_nodes'      : ov_disconnected_nodes,
        'disconnected_travellers' : ov_disconnected_travellers,
        'RSGC'                    : round(ov_n_nodes / default_n_nodes, 3),
    })

    # Recalculate how pax would flow after disruption with OV alternative TT across target edge, using the same demand model as in the main run
    G_ov_alternative_demand = demand.assign_flows(G_ov_subgraph, scale_factor = scale_factor, decay = decay, apply_override=False, morning_demand=morning_demand)
    disrupted_recalulated_pax_flow = G_ov_alternative_demand[target1][target2]['flow']
    disrupted_recalulated_pax_min_flow = G_ov_alternative_demand[target1][target2]['pax_min']
    result_tracks_ov_alternative.update({
        'disrupted_recalulated_pax_flow'     : disrupted_recalulated_pax_flow,
        'disrupted_recalulated_pax_min_flow' : disrupted_recalulated_pax_min_flow,
        'delta_recalculated_flow' : disrupted_recalulated_pax_flow - disrupted_pax_flow,
    })
    

    # Metrics describing the disruption itself
    shared_track_data = {
        'tt_default'             : tt_default,
        'tt_alt'                 : tt_alt,
        'tt_ipv'                 : tt_ipv,
        'tt_ov'                  : tt_ov,
        'disrupted_pax_flow'     : disrupted_pax_flow,
        'disrupted_pax_min_flow' : disrupted_pax_min_flow,
        'ipv_capacity'           : ipv_capacity,
        'delta_ipv_capacity'     : delta_ipv_capacity,
        'ov_capacity'            : ov_capacity,
        'delta_ov_capacity'      : delta_ov_capacity,
        'total_alt_capacity'     : ipv_capacity + ov_capacity,
        'delta_alt_capacity'     : (ipv_capacity + ov_capacity) - disrupted_pax_flow,
    }
    result_tracks_no_alternative.update(shared_track_data)
    result_tracks_ipv_alternative.update(shared_track_data)
    result_tracks_ov_alternative.update(shared_track_data)

    return result_tracks_no_alternative, result_tracks_ipv_alternative, result_tracks_ov_alternative


def disrupt_nodes(G_services:nx.Graph, G_tracks: nx.Graph, G_ipv: nx.Graph, G_ov: nx.Graph, run_exp:bool=False, morning_demand:bool=True, disrupt_services:bool = True) -> pd.DataFrame:
    """
    Disrupts track nodes one-by-one.

    Computes at the same time the metrics for:
        - the disrupted track graph with no bus replacements considered,
        - the track graph when bus replacements are considered (ipv or ov),
        - the service graph when bus replacements are considered (ipv or ov),
    """

    # Do I want to run the disruption procedure or load the last run?
    if run_exp:
        start_time = time.time()
        print(f"Node disruptions started at: {time.strftime('%H:%M:%S')}")
        track_nodes = [(n,e) for n,e in G_tracks.nodes(data=True)]

        # Initialize output rows with default metrics
        result_tracks_no_alternative = {}
        result_tracks_ipv_alternative = {}
        result_tracks_ov_alternative = {}

        result_services_no_alternative = {}
        result_services_ipv_alternative = {}
        result_services_ov_alternative = {}

        # Track initialization
        default_track_metrics = metrics.node_metrics(G_tracks)
        result_tracks_ipv_alternative[('default')] = dict(default_track_metrics)
        result_tracks_ov_alternative[('default')]  = dict(default_track_metrics)
        result_tracks_no_alternative[('default')]  = dict(default_track_metrics)

        # Service initialization
        default_service_metrics = metrics.node_metrics(G_services)
        result_services_no_alternative[('default')]  = dict(default_service_metrics)
        result_services_ipv_alternative[('default')] = dict(default_service_metrics)
        result_services_ov_alternative[('default')]  = dict(default_service_metrics)

        # Default size
        default_n_nodes = G_tracks.number_of_nodes()
        default_n_nodes_services = G_services.number_of_nodes()

        # IPV speed alternatives for missing edges
        median_speed = np.nanmedian(list(nx.get_edge_attributes(G_tracks,"speed").values()))

        # Precompute each service edge's underlying track-path node set
        service_edge_path_nodes = [
            (src, dst, set(data.get('track_nodes', [])))
            for src, dst, data in G_services.edges(data=True)
        ]

        # Disruption loop
        i = 0
        t = 0
        for node in track_nodes:
            i += 1
            node_name  = node[0]
            node_attrs = node[1]

            # Escape if yard node
            if node_attrs.get("Type") in ("yard"):
                print(f"escaping track disruption loop because {node_name} is a yard")
                continue

            neighbors = list(G_tracks.neighbors(node_name))
            neighbors_dict = dict(G_tracks[node_name])
            graph_connected = True



            ##### INFRA NODES #####
            # Create the graph copies for each disruption scenario
            G_ipv_alternative = G_tracks.copy()  # The graph where travel times are adjusted
            G_ov_alternative  = G_tracks.copy()  # The graph where ov alternatives are used
            G_disrupted       = G_tracks.copy()  # The graph from which elements are removed

            # Default per-neighbor travel times before removal
            tt_default_dict = {n: attrs['travel_time'] for n, attrs in neighbors_dict.items()}
            tt_default_values = list(tt_default_dict.values())
            tt_default_avg = np.nanmean(tt_default_values) if tt_default_values and not np.all(np.isnan(tt_default_values)) else np.nan
            tt_default_sum = np.nansum(tt_default_values) if tt_default_values and not np.all(np.isnan(tt_default_values)) else np.nan

            # Remove the node
            G_disrupted.remove_node(node_name)

            # Alternative travel time between each pair of former neighbors, routed on G_disrupted where node_name is already removed. 
            tt_alt_dict = {}
            for j, src in enumerate(neighbors):
                for tgt in neighbors[j + 1:]:
                    try:
                        tt_alt_dict[(src, tgt)] = nx.shortest_path_length(G_disrupted, source=src, target=tgt, weight='travel_time')
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        tt_alt_dict[(src, tgt)] = np.nan


            tt_alt_values = list(tt_alt_dict.values())
            tt_alt_avg = np.nanmean(tt_alt_values) if tt_alt_values and not np.all(np.isnan(tt_alt_values)) else np.nan
            tt_alt_sum = np.nansum(tt_alt_values) if tt_alt_values and not np.all(np.isnan(tt_alt_values)) else np.nan

            # Get the largest subgraph + other statistics about this disruption scenario
            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disrupted, morning_demand=morning_demand)
            graph_connected = (n_components == 1)

            # Initialize the outputs for the non-replacement situation
            result_tracks_no_alternative[node_name]  = metrics.node_metrics(G_subgraph, node=node_name)

            result_tracks_no_alternative[node_name].update({
                'RSGC' : round(n_nodes / default_n_nodes, 3),
                'graph_connected' : graph_connected,
                'n_components' : n_components,
                'disconnected_travellers' : disconnected_travellers,
                'disconnected_nodes' : disconnected_nodes,
            })

            disrupted_pax_flow_dict     = {n: round(attrs['flow'], 0)    for n, attrs in neighbors_dict.items()}
            disrupted_pax_min_flow_dict = {n: round(attrs['pax_min'], 0) for n, attrs in neighbors_dict.items()}
            disrupted_pax_flow_sum      = round(np.sum(list(disrupted_pax_flow_dict.values())))
            disrupted_pax_min_flow_sum  = round(np.sum(list(disrupted_pax_min_flow_dict.values())))

            # IPV alternative - guard against nodes which might not have ipv service (aansluitings, ghosts)
            ipv_capacity_dict = {}
            for n in neighbors_dict:
                if G_services.has_edge(node_name, n) or G_services.has_edge(n, node_name):
                    cap = G_services[node_name][n]['capacity'] if G_services.has_edge(node_name, n) else G_services[n][node_name]['capacity']
                    ipv_capacity_dict[n] = 400.0 if pd.isna(cap) else cap
                else:
                    ipv_capacity_dict[n] = 400.0  # pass from constants!
            ipv_capacity_sum = round(np.sum(list(ipv_capacity_dict.values())))
            delta_ipv_capacity_sum = ipv_capacity_sum - disrupted_pax_flow_sum

            # Assign IPV travel time to each incident edge, falling back to median-speed estimate if no G_ipv edge exists
            tt_ipv_dict = {}
            for n in neighbors:
                if G_ipv.has_edge(node_name, n) or G_ipv.has_edge(n, node_name):
                    tt_ipv_dict[n] = G_ipv[node_name][n]['ipv_travel_time'] if G_ipv.has_edge(node_name, n) else G_ipv[n][node_name]['ipv_travel_time']
                else:
                    tt_ipv_dict[n] = median_speed * G_tracks[node_name][n]['geo_length']
                    t += 1

                # Assign new travel times to track graph edge
                if G_ipv_alternative.has_edge(node_name, n):
                    G_ipv_alternative[node_name][n]['travel_time'] = tt_ipv_dict[n]
                    G_ipv_alternative[node_name][n]['pax_min'] = tt_ipv_dict[n] * G_ipv_alternative[node_name][n]['flow']

            tt_ipv_avg = np.mean(list(tt_ipv_dict.values())) if tt_ipv_dict else np.nan
            tt_ipv_sum = np.sum(list(tt_ipv_dict.values())) if tt_ipv_dict else np.nan

            # No need for subgraph because graph will always be connected (no node removed, only travel times changed)
            result_tracks_ipv_alternative[(node_name)] = metrics.node_metrics(G_ipv_alternative, node=node_name)

            ##### OV Alternative #####
            ov_capacity_dict = {}
            for n in neighbors_dict:
                if G_services.has_edge(node_name, n) or G_services.has_edge(n, node_name):
                    cap = G_services[node_name][n]['ov_capacity'] if G_services.has_edge(node_name, n) else G_services[n][node_name]['ov_capacity']
                    ov_capacity_dict[n] = 400.0 if pd.isna(cap) else cap
                else:
                    ov_capacity_dict[n] = 400.0  # pass from constants!
            ov_capacity_sum = round(np.nansum(list(ov_capacity_dict.values())))
            try:
                delta_ov_capacity_sum = ov_capacity_sum - disrupted_pax_flow_sum 
            except:
                delta_ov_capacity_sum = 0 - disrupted_pax_flow_sum 

            tt_ov_dict = {}
            for n in neighbors:
                if G_ov.has_edge(node_name, n) or G_ov.has_edge(n, node_name):
                    tt_ov_dict[n] = G_ov[node_name][n]['travel_time_ov_min'] if G_ov.has_edge(node_name, n) else G_ov[n][node_name]['travel_time_ov_min']
                    G_ov_alternative[node_name][n]['travel_time'] = tt_ov_dict[n]
                    G_ov_alternative[node_name][n]['pax_min'] = tt_ov_dict[n] * G_ov_alternative[node_name][n]['flow']
                else:
                    # If no ov edge exists then do not fit some value, the edge is simply removed
                    if G_ov_alternative.has_edge(node_name, n):
                        G_ov_alternative.remove_edge(node_name, n)
                        graph_connected = False
                    tt_ov_dict[n] = np.nan

            tt_ov_values = list(tt_ov_dict.values())
            tt_ov_avg = np.nanmean(tt_ov_values) if tt_ov_values and not np.all(np.isnan(tt_ov_values)) else np.nan
            tt_ov_sum = np.nansum(tt_ov_values) if tt_ov_values and not np.all(np.isnan(tt_ov_values)) else np.nan

            # Results that are the same for all alternatives
            universal_data = {
                'tt_default_dict'             : tt_default_dict,
                'tt_default_avg'              : tt_default_avg,
                'tt_default_sum'              : tt_default_sum,
                'tt_alt_dict'                 : tt_alt_dict,
                'tt_alt_avg'                  : tt_alt_avg,
                'tt_alt_sum'                  : tt_alt_sum,
                'tt_ipv_dict'                 : tt_ipv_dict,
                'tt_ipv_avg'                  : tt_ipv_avg,
                'tt_ipv_sum'                  : tt_ipv_sum,
                'tt_ov_dict'                  : tt_ov_dict,
                'tt_ov_avg'                   : tt_ov_avg,
                'tt_ov_sum'                   : tt_ov_sum,
                'disrupted_pax_flow_dict'     : disrupted_pax_flow_dict,
                'disrupted_pax_flow_sum'      : disrupted_pax_flow_sum,
                'disrupted_pax_min_flow_dict' : disrupted_pax_min_flow_dict,
                'disrupted_pax_min_flow_sum'  : disrupted_pax_min_flow_sum,
                'ipv_capacity_dict'           : ipv_capacity_dict,
                'ipv_capacity_sum'            : ipv_capacity_sum,
                'delta_ipv_capacity_sum'      : delta_ipv_capacity_sum,
                'ov_capacity_dict'            : ov_capacity_dict,
                'ov_capacity_sum'             : ov_capacity_sum,
                'delta_ov_capacity_sum'       : delta_ov_capacity_sum,
                'total_alt_capacity'          : ipv_capacity_sum + ov_capacity_sum,
                'delta_alt_capacity'          : (ipv_capacity_sum + ov_capacity_sum) - disrupted_pax_flow_sum,
            }

            # OV specific information since it can be disconnected
            G_ov_subgraph, stranded_travelers, n_components, n_nodes_largest, non_largest_nodes = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_tracks_ov_alternative[node_name] = metrics.node_metrics(G_ov_subgraph, node=node_name)
            disrupted_graph_data_ov = {
                'n_nodes'                     : n_nodes_largest,
                'graph_connected'             : graph_connected,
                'n_components'                : n_components,
                'disconnected_nodes'          : non_largest_nodes,
                'RSGC'                        : round(n_nodes_largest / default_n_nodes,3),
                'disconnected_travellers'     : stranded_travelers,
            }

            # Update all metric outputs with this data
            result_tracks_no_alternative[node_name].update(universal_data)
            result_tracks_ipv_alternative[node_name].update(universal_data)
            result_tracks_ov_alternative[node_name].update(disrupted_graph_data_ov)
            result_tracks_ov_alternative[node_name].update(universal_data)


            ##### SERVICE NODES #####
            # Escape clause for if only want to look at track disruptions (no replacement scenario)
            if disrupt_services == False:
                continue

            # Escape clause for if a yard or aansluiting is being disrupted
            if G_tracks.nodes[node_name].get("Type") in ("connection","closed"):
                print(f"Disrupted {i}/{default_n_nodes} track nodes | Current node: {node_name}")
                print(f"Escaped service disruption iteration due to {node_name} being a connection / closed type.")
                continue

            G_ipv_alternative = G_services.copy()  # Travel time adjusted graph (IPV)
            G_ov_alternative  = G_services.copy()
            G_disruption      = G_services.copy()  # Node/edge removed graph

            # Remove the node itself if it exists
            if G_disruption.has_node(node_name):
                G_disruption.remove_node(node_name)

            # Remove affected overlapping service edges
            affected_tracks = [
                (src, dst) for src, dst, path_nodes in service_edge_path_nodes
                if node_name in path_nodes
            ]

            G_disruption.remove_edges_from(affected_tracks)
            G_subgraph, disconnected_travellers, n_components, n_nodes, disconnected_nodes = _get_subgraph(G_disruption, morning_demand=morning_demand)

            if n_components == 1:
                graph_connected = True
            else:
                graph_connected = False

            # Alternative travel time between each pair of former service-neighbors
            service_neighbors = list(G_services.neighbors(node_name)) if G_services.has_node(node_name) else []
            tt_alt_dict_services = {}
            for j, src in enumerate(service_neighbors):
                for tgt in service_neighbors[j + 1:]:
                    try:
                        tt_alt_dict_services[(src, tgt)] = nx.shortest_path_length(G_disruption, source=src, target=tgt, weight='travel_time')
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        tt_alt_dict_services[(src, tgt)] = np.nan

            tt_alt_values_services = list(tt_alt_dict_services.values())
            tt_alt_avg_services = np.nanmean(tt_alt_values_services) if tt_alt_values_services and not np.all(np.isnan(tt_alt_values_services)) else np.nan
            tt_alt_sum_services = np.nansum(tt_alt_values_services) if tt_alt_values_services and not np.all(np.isnan(tt_alt_values_services)) else np.nan

            # Initialize outputs for all three scenarios on the no-alternative subgraph 
            base_service_metrics = metrics.node_metrics(G_subgraph, node=node_name)
            result_services_no_alternative[(node_name)]  = dict(base_service_metrics)
            result_services_ipv_alternative[(node_name)] = dict(base_service_metrics)
            result_services_ov_alternative[(node_name)]  = dict(base_service_metrics)

            # Disruption-specific metrics 
            result_services_no_alternative[(node_name)].update({
                'n_nodes'                 : n_nodes,
                'graph_connected'         : graph_connected,
                'n_components'            : n_components,
                'disconnected_nodes'      : disconnected_nodes,
                'disconnected_travellers' : disconnected_travellers,
                'RSGC'                    : round(n_nodes / default_n_nodes_services, 3),
            })

            # Guard against the node not existing as a real service stop
            if not G_services.has_node(node_name):
                print(f"escaping service loop, no node exists for {node_name}")
                continue

            ### IPV alternative ###
            ipv_tt_affected = None
            tt_ipv_dict_services = {}
            capacity_ipv_dict_services = {}
            for src, dst in affected_tracks:
                if G_ipv.has_edge(src, dst):
                    ipv_tt_affected = G_ipv[src][dst].get('ipv_travel_time')
                    ipv_capacity = G_services[src][dst].get('capacity')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected
                        tt_ipv_dict_services[(src, dst)] = ipv_tt_affected
                        capacity_ipv_dict_services[(src,dst)] = ipv_capacity
                elif G_ipv.has_edge(dst, src):
                    ipv_tt_affected = G_ipv[dst][src].get('ipv_travel_time')
                    ipv_capacity = G_services[src][dst].get('capacity')
                    if ipv_tt_affected is not None and G_ipv_alternative.has_edge(src, dst):
                        G_ipv_alternative[src][dst]['travel_time'] = ipv_tt_affected
                        tt_ipv_dict_services[(src, dst)] = ipv_tt_affected
                        capacity_ipv_dict_services[(src,dst)] = ipv_capacity

            tt_ipv_values_services = list(tt_ipv_dict_services.values())
            tt_ipv_avg_services = np.mean(tt_ipv_values_services) if tt_ipv_values_services else np.nan
            tt_ipv_sum_services = np.sum(tt_ipv_values_services) if tt_ipv_values_services else np.nan

            result_services_ipv_alternative[(node_name)] = metrics.node_metrics(G_ipv_alternative, node=node_name)

            ### OV alternative ###
            tt_ov_dict_services = {}
            capacity_ov_dict_services = {}
            for src, dst in affected_tracks:
                if G_ov.has_edge(src, dst) or G_ov.has_edge(dst, src):
                    ov_tt_affected = G_ov[src][dst]['travel_time_ov_min'] if G_ov.has_edge(src, dst) else G_ov[dst][src]['travel_time_ov_min']
                    ov_capacity = G_services[src][dst].get('ov_capacity')
                    tt_ov_dict_services[(src, dst)] = ov_tt_affected
                    capacity_ov_dict_services[(src,dst)] = ov_capacity
                    if G_ov_alternative.has_edge(src, dst):
                        G_ov_alternative[src][dst]['travel_time'] = ov_tt_affected
                        G_ov_alternative[src][dst]['pax_min'] = ov_tt_affected * G_ov_alternative[src][dst]['flow']
                else:
                    # No ov alternative exists for this affected edge
                    tt_ov_dict_services[(src, dst)] = np.nan
                    if G_ov_alternative.has_edge(src, dst):
                        G_ov_alternative.remove_edge(src,dst)

            tt_ov_values_services = list(tt_ov_dict_services.values())
            tt_ov_avg_services = np.nanmean(tt_ov_values_services) if tt_ov_values_services and not np.all(np.isnan(tt_ov_values_services)) else np.nan
            tt_ov_sum_services = np.nansum(tt_ov_values_services) if tt_ov_values_services and not np.all(np.isnan(tt_ov_values_services)) else np.nan

            capacity_ov_values_services = list(capacity_ov_dict_services.values())
            capacity_ov_sum_services = np.sum(capacity_ov_values_services) if capacity_ov_values_services else np.nan
            capacity_ipv_values_services = list(capacity_ipv_dict_services.values())
            capacity_ipv_sum_services = np.sum(capacity_ipv_values_services) if capacity_ipv_values_services else np.nan

            universal_data.update ({
                'tt_alt_dict'        : tt_alt_dict_services,
                'tt_alt_avg'         : tt_alt_avg_services,
                'tt_alt_sum'         : tt_alt_sum_services,
                'tt_ipv_dict'        : tt_ipv_dict_services,
                'tt_ipv_avg'         : tt_ipv_avg_services,
                'tt_ipv_sum'         : tt_ipv_sum_services,
                'tt_ov_dict'         : tt_ov_dict_services,
                'tt_ov_avg'          : tt_ov_avg_services,
                'tt_ov_sum'          : tt_ov_sum_services,
                'ov_capacity_dict'   : capacity_ov_dict_services,
                'ov_capacity_sum'    : capacity_ov_sum_services,
                'ipv_capacity_dict'  : capacity_ipv_dict_services,
                'ipv_capacity_sum'   : capacity_ipv_sum_services,
                'total_alt_capacity' : capacity_ipv_sum_services + capacity_ov_sum_services,
                'delta_alt_capacity' : (capacity_ipv_sum_services + capacity_ov_sum_services) - disrupted_pax_flow_sum,
            })

            # Recompute structural metrics using OV graph
            G_ov_subgraph_services, stranded_travelers, n_components, n_nodes, non_largest_nodes = _get_subgraph(G_ov_alternative, morning_demand=morning_demand)
            result_services_ov_alternative[(node_name)].update(metrics.node_metrics(G_ov_subgraph_services, node=node_name))

            # update all returning rows with the alternative travel times
            result_services_ipv_alternative[(node_name)].update(universal_data)
            result_services_ov_alternative[(node_name)].update(universal_data)
            result_services_no_alternative[(node_name)].update(universal_data)

            if n_components == 1:
                graph_connected = True
            else:
                graph_connected = False

            # Separate update for ov since have different values
            disrupted_graph_data_ov = {
                'RSGC'    : round(n_nodes / default_n_nodes_services, 3),
                'n_nodes' : n_nodes,
                'graph_connected' : graph_connected,
                'n_components' : n_components,
                'disconnected_nodes' : non_largest_nodes,
                'disconnected_travellers': stranded_travelers,
            }
            result_services_ov_alternative[(node_name)].update(disrupted_graph_data_ov)

            print(f"Disrupted {i}/{default_n_nodes} track nodes | Current node: {node_name}")



        print(f"Extrapolated {t} ipv travel times to track graph")

        def _dict_to_json(results:dict, filename:str) -> pd.DataFrame:
            # Takes the result dict and stores it as json based on dict name
            metric_df = pd.DataFrame.from_dict(results, orient='index')
            metric_df.index.name = 'node'
            metric_df.to_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            return metric_df

        node_metrics_tracks_no_alternative = _dict_to_json(result_tracks_no_alternative, filename='node_disruption_data_tracks_no_alternative')
        node_metrics_tracks_ipv_alt        = _dict_to_json(result_tracks_ipv_alternative, filename='node_disruption_data_tracks_ipv_alt')
        node_metrics_tracks_ov_alt         = _dict_to_json(result_tracks_ov_alternative, filename='node_disruption_data_tracks_ov_alt')

        node_metrics_services_no_alternative = _dict_to_json(result_services_no_alternative, filename='node_disruption_data_services_no_alternative')
        node_metrics_services_ipv_alt        = _dict_to_json(result_services_ipv_alternative, filename='node_disruption_data_services_ipv_alt')
        node_metrics_services_ov_alt         = _dict_to_json(result_services_ov_alternative, filename='node_disruption_data_services_ov_alt')

        total_time = time.time() - start_time
        print(f"Node disruptions finished at: {time.strftime('%H:%M:%S')}  (total: {total_time:.0f}s)")

    else:
        # Load prior run
        def _json_to_df(filename:str)->pd.DataFrame:
            # Takes the passed name and loads the json into a df
            df = pd.read_json(sf.get_dir(f"export/{filename}.json"), orient='columns')
            return df

        node_metrics_tracks_no_alternative = _json_to_df(filename='node_disruption_data_tracks_no_alternative')
        node_metrics_tracks_ipv_alt        = _json_to_df(filename='node_disruption_data_tracks_ipv_alt')
        node_metrics_tracks_ov_alt         = _json_to_df(filename='node_disruption_data_tracks_ov_alt')

        node_metrics_services_no_alternative = _json_to_df(filename='node_disruption_data_services_no_alternative')
        node_metrics_services_ipv_alt        = _json_to_df(filename='node_disruption_data_services_ipv_alt')
        node_metrics_services_ov_alt         = _json_to_df(filename='node_disruption_data_services_ov_alt')

        print("loaded node disruptions")

    return node_metrics_tracks_no_alternative, node_metrics_tracks_ipv_alt, node_metrics_tracks_ov_alt, node_metrics_services_no_alternative, node_metrics_services_ipv_alt, node_metrics_services_ov_alt

import pandas as pd
import networkx as nx
import numpy as np
import powerlaw
import modules.supporting_functions as sf

"""
This stores the functions used to compute statistics about the disruptions and graphs.

Again refer to edge_metrics on the bottom to see the current version, ic_segments and nodes are being re-written
"""

def scale_factor(G: nx.Graph) -> float:
    """
    Creates a histogram of node distributions from the graph,
    fits a power law, and returns the scale-factor (alpha) value.
    """
    degree_sequence = [d for n, d in G.degree() if d > 0]
    fit = powerlaw.Fit(degree_sequence, verbose=0)
    return fit.alpha

def natural_connectivity(largest_component: nx.Graph, n: int) -> float:
    eigenvalues = np.linalg.eigvalsh(nx.to_numpy_array(largest_component))
    return (1 / (n - np.log(n))) * np.log(np.sum(np.exp(eigenvalues)) / n)

def conductance(largest_component: nx.Graph, n: int) -> float:
    mu          = np.linalg.eigvalsh(nx.laplacian_matrix(largest_component).toarray())
    mu_nonzero  = mu[mu > 1e-10]
    return (n - 1) / (n * np.sum(1 / mu_nonzero))

def degree_diversity(degrees: list) -> float:
    return (np.sum(np.array(degrees) ** 2)) / np.sum(degrees)

def _structural_metrics(G) -> dict:
    """
    Calculates every graph-level structural metric for both nodes and edges.
    """
    components = list(nx.connected_components(G))
    n_nodes    = len(max(components, key=len))
    degrees    = [d for n, d in G.degree()]

    n = len(G)
    denom = n * (n - 1)

    # One BFS pass: APL_u (sum of hop distances) + GE (sum of 1/distance)
    apl_u_total = 0
    ge_total = 0
    for u in G:
        lengths = nx.single_source_shortest_path_length(G, u)
        apl_u_total += sum(lengths.values())  # integer hop counts - exact
        for distance in lengths.values():
            if distance > 0:
                ge_total += 1 / distance

    # One Dijkstra pass: APL_tt (sum of travel times) + diameter (max eccentricity)
    apl_tt_total = 0
    diameter = 0
    for u in G:
        lengths = nx.single_source_dijkstra_path_length(G, u, weight='travel_time')
        for l in lengths.values():
            apl_tt_total += l
        eccentricity = max(lengths.values())
        if eccentricity > diameter:
            diameter = eccentricity

    return {
        'n_nodes'      : n_nodes,
        'n_components' : len(components),

        # Structural metrics
        'APL_u'      : apl_u_total / denom, # The average number of edges required to traverse any two nodes
        'APL_tt'     : apl_tt_total / denom, # The average travel time to traverse any two nodes
        'APL_ftt'    : nx.average_shortest_path_length(G, weight='pax_min'), # The average number of passenger-minutes for some trip between two nodes
        'APL_flow'   : nx.average_shortest_path_length(G, weight='flow'), # The average number of pax travelling between any two nodes
        'diameter'   : diameter, # What is the longest travel time for the network?

        # Connectivity metrics
        'GE'                     : ge_total / denom if denom != 0 else 0, # How quickly can any two nodes reach each other
        'scaling_factor'         : scale_factor(G), # Exponent of the degree distribution
        'avg_degree'             : np.mean(degrees), # What is the average degree of a node
        'avg_cluster_coef'       : nx.average_clustering(G, weight='travel_time'), # How likely it is that two neighbours of a node are also connected to each other
        'degree_diversity'       : degree_diversity(degrees), # Molloy-Reed Parameter, the higher the more nodes need to be removed to disconnect network
        'conductance'            : conductance(G, n_nodes), # Reflects both the number and length of paths between node pairs
        'natural_connectivity'   : natural_connectivity(G, n_nodes), # An approximate indicator of redundancy or the number of alternative routes
        'algebraic_connectivity' : nx.algebraic_connectivity(G, weight='travel_time', normalized=False), # Degree of graph connectivity
    }

def node_metrics(G, node:str=None) -> dict:
    """
    Generic function that initializes metrics and calculates them for a graph.
    Must have a connected graph passed to it.
    """

    s = _structural_metrics(G)

    row = {'node' : node}
    row.update({
        # Disruption information
        'n_nodes'            : s['n_nodes'],           # Number of nodes in the graph
        'graph_connected'    : True,                   # Is the graph fully connected?
        'n_components'       : s['n_components'],      # How many components are there?
        'disconnected_nodes' : None,                   # Nodes that are not part of the largest component

        # Structural metrics
        'APL_u'      : s['APL_u'],
        'APL_tt'     : s['APL_tt'],
        'APL_ftt'    : s['APL_ftt'],
        'APL_flow'   : s['APL_flow'],
        'diameter'   : s['diameter'],

        # Connectivity metrics
        'GE'                     : s['GE'],
        'RSGC'                   : 1.0, # How much the network shrunk after an edge was disrupted
        'scaling_factor'         : s['scaling_factor'],
        'avg_degree'             : s['avg_degree'],
        'avg_cluster_coef'       : s['avg_cluster_coef'],
        'degree_diversity'       : s['degree_diversity'],
        'conductance'            : s['conductance'],
        'natural_connectivity'   : s['natural_connectivity'],
        'algebraic_connectivity' : s['algebraic_connectivity'],

        # Node dictionaries
        'tt_default_dict'             : None,
        'tt_alt_dict'                 : None,
        'tt_alt_avg'                  : None,
        'tt_alt_sum'                  : None,
        'tt_ipv_dict'                 : None,
        'tt_ipv_avg'                  : None,
        'tt_ipv_sum'                  : None,
        'tt_ov_dict'                  : None,
        'tt_ov_avg'                   : None,
        'tt_ov_sum'                   : None,

        # Passenger metrics
        'disconnected_travellers'     : None,
        'disrupted_pax_flow_dict'     : None,
        'disrupted_pax_flow_sum'      : None,
        'disrupted_pax_min_flow_dict' : None,
        'disrupted_pax_min_flow_sum'  : None,
        'ipv_capacity_dict'           : None,
        'ipv_capacity_sum'            : None,
        'delta_ipv_capacity_sum'      : None,
        'ov_capacity_dict'            : None,
        'ov_capacity_sum'             : None,
        'delta_ov_capacity_sum'       : None,
    })

    return row

def edge_metrics(G, source:str=None, target:str=None, node_disruptions:bool=False) -> dict:
    """
    Generic function that initializes metrics and calculates them for a graph.
    Must have a connected graph passed to it.
    """

    s = _structural_metrics(G)

    # Target type
    if node_disruptions:
        row = {'node' : source}
    else:
        row = {
            'source' : source,
            'target' : target,}

    row.update({
        # Disruption information
        'n_nodes'            : s['n_nodes'],           # Number of nodes in the graph
        'graph_connected'    : True,                   # Is the graph fully connected?
        'n_components'       : s['n_components'],      # How many components are there?
        'disconnected_nodes' : None,                   # Nodes that are not part of the largest component

        # Structural metrics
        'tt_default' : None, # The normal travel time across this edge
        'tt_alt'     : None, # The non-bus alternative travel time (if G = connected)
        'tt_ipv'     : None, # The ipv bus travel time across this edge (if available)
        'tt_ov'      : None, # The ov bus travel time across this edge (if available)
        'APL_u'      : s['APL_u'],
        'APL_tt'     : s['APL_tt'],
        'APL_ftt'    : s['APL_ftt'],
        'APL_flow'   : s['APL_flow'],
        'diameter'   : s['diameter'],

        # Connectivity metrics
        'GE'                     : s['GE'],
        'RSGC'                   : 1.0, # How much the network shrunk after an edge was disrupted
        'scaling_factor'         : s['scaling_factor'],
        'avg_degree'             : s['avg_degree'],
        'avg_cluster_coef'       : s['avg_cluster_coef'],
        'degree_diversity'       : s['degree_diversity'],
        'conductance'            : s['conductance'],
        'natural_connectivity'   : s['natural_connectivity'],
        'algebraic_connectivity' : s['algebraic_connectivity'],

        # Passenger metrics - require a disruption to get a value
        'disconnected_travellers': None, # Demand at nodes that are not part of the largest component / how many need to take ipv to get to rest of network
        'disrupted_pax_flow'     : None, # How many pax travel across this edge by default
        'disrupted_pax_min_flow' : None, # How many passenger-minutes go across this edge by defaut
        'ipv_capacity'           : None, # What is the ipv capacity across this edge?
        'delta_ipv_capacity'     : None, # What is the flow - capacity for this edge?
        'ov_capacity'            : None,
        'delta_ov_capacity'      : None,
        'total_alt_capacity'     : None,
        'delta_alt_capacity'     : None,  
    })

    return row

lower_is_more_impactful = {
    "GE_u", "largest_component_size", "RSGC", "avg_degree",
    "degree_diversity", "avg_cluster_coef", "natural_connectivity",
    "algebraic_connectivity", "conductance", "n_nodes", "delta_ipv_capacity", "delta_ov_capacity","delta_alt_capacity",
}

def highest_impacts_results(
    edge_metrics_tracks_no_alternative:pd.DataFrame, edge_metrics_tracks_ipv_alt:pd.DataFrame, edge_metrics_tracks_ov_alt:pd.DataFrame, edge_metrics_services_no_alternative:pd.DataFrame, edge_metrics_services_ipv_alt:pd.DataFrame, edge_metrics_services_ov_alt:pd.DataFrame,disruption_type: str = 'edge') -> pd.DataFrame:
    """
    For every metric get the element which had the greatest impact.
    Returns a df with metric, element, change.
    """
    col_names = ['tracks w/o alt','tracks w/ ipv','tracks w/ ov','services w/o alt','services w/ ipv','services w/ ov'] 
    dfs = [edge_metrics_tracks_no_alternative, edge_metrics_tracks_ipv_alt, edge_metrics_tracks_ov_alt, edge_metrics_services_no_alternative, edge_metrics_services_ipv_alt, edge_metrics_services_ov_alt]
    default_key = ('default', 'default')

    metrics = edge_metrics_tracks_no_alternative.columns.tolist()
    result = pd.DataFrame(index=metrics, columns=col_names, dtype=object)

    for metric in metrics:
        if metric in ['source','target','graph_connected','disconnected_nodes','tt_default']: continue
        worst_direction = 'decrease' if metric in lower_is_more_impactful else 'increase'

        for col_name, df in zip(col_names, dfs):
            default_val = None
            disrupted_val = None
            worst_idx = None
            worst_delta = None
            element = None

            try:
                default_val = df.loc[default_key, metric]
                disrupted = df.drop(index=default_key)[metric]

                default_is_nan = pd.isna(default_val)
                disrupted_all_nan = disrupted.isna().all()

                if default_is_nan and disrupted_all_nan:
                    result.at[metric, col_name] = (None, None, None, None)

                elif default_is_nan:
                    disrupted_valid = disrupted.dropna()
                    if worst_direction == 'decrease':
                        worst_idx = disrupted_valid.idxmin()
                    else:
                        worst_idx = disrupted_valid.idxmax()
                    disrupted_val = disrupted_valid[worst_idx]
                    element = worst_idx if disruption_type == 'edge' else (
                        worst_idx if not isinstance(worst_idx, tuple) else str(worst_idx)
                    )
                    result.at[metric, col_name] = (element, None, disrupted_val, None)

                elif disrupted_all_nan:
                    # All disrupted values are NaN, only default is known
                    result.at[metric, col_name] = (None, default_val, None, None)

                else:
                    # Normal path: drop any partially NaN disrupted rows before ranking
                    disrupted = disrupted.dropna()
                    if worst_direction == 'decrease':
                        delta = disrupted - default_val
                        worst_idx = delta.idxmin()
                    else:
                        delta = disrupted - default_val
                        worst_idx = delta.idxmax()

                    disrupted_val = disrupted[worst_idx]
                    worst_delta = delta[worst_idx]
                    element = worst_idx if disruption_type == 'edge' else (
                        worst_idx if not isinstance(worst_idx, tuple) else str(worst_idx)
                    )
                    result.at[metric, col_name] = (element, default_val, disrupted_val, worst_delta)

            except TypeError:
                result.at[metric, col_name] = None

            # Format element name: keep tuple for edges, plain name otherwise
            if disruption_type == 'edge':
                element = worst_idx  
            else:
                element = worst_idx if not isinstance(worst_idx, tuple) else str(worst_idx)

            result.at[metric,col_name] = {
                'name' : element,
                'default_value' : default_val,
                'disrupted_value' : disrupted_val,
                'delta' : worst_delta,}
            
            if worst_delta == 0:
                result.at[metric,col_name] = 'All values the same'

    result.drop(labels=['source','target','graph_connected','n_components','disconnected_nodes','tt_default'], inplace=True, errors='ignore')
    result.to_csv(sf.get_dir('export/worst_disruptions.csv'), header=True,index=True)

    return result
import pandas   as pd
import networkx as nx
import os

"""
This module contains the functions that are called in different places,
generally anything useful that isn't directly related to data preparation.
"""

def set_node_attributes_from_dataframe(
    G: nx.Graph,
    stations_df: pd.DataFrame
) -> nx.Graph:
    """
    Sets node attributes on G by matching node names to the 'Name' column
    in the stations DataFrame.

    Also adds:
        - is_passthrough : bool
            True if node is not an active station node
    """

    # The values from the json track nodes that are relevant
    attrs = [
        "TravelersPerDay",
        "BoardingDeboarding",
        "Transfering",
        "reizigers_station",
        "station_catchment",
        "ic_station",
        "demand",
        "full_demand",
        "MorningRush",
        "MorningDemand",
        "Type",
    ]

    # These nodes should be ignored for routing / demand flow purposes
    PASSTHROUGH_NODES = {
        "Breda High Speed aansluiting",
        "Breda aansluiting",
        "Duivendrecht aansluiting west",
        "Muiderberg aansluiting",
        "Naarden-Bussum aansluiting",
        "Zevenbergsehoek aansluiting",
        "Heerlen de Kissel",
        "Hoofddorp Midden",
        "Bokkeduinen",
        "Woerden Molenvliet",
        "Amsterdam Riekerpolder",
        "Sappemeer Oost",
    }

    for node in G.nodes:
        G.nodes[node]["is_passthrough"] = node in PASSTHROUGH_NODES

        if node in stations_df.index:
            for attr in attrs:
                if attr in stations_df.columns:
                    G.nodes[node][attr] = stations_df.at[node, attr]
        else:
            # Populate missing nodes with zeros
            for attr in attrs:
                G.nodes[node][attr] = 0.0

    return G

def graph_to_dataframes(G: nx.Graph) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Extracts all node and edge attributes from a NetworkX graph into DataFrames.
    Nodes indexed on node name
    Edges indexed on source and target nodes

    Args:
        G : NetworkX graph
    Returns:
        (nodes_df, edges_df) tuple of DataFrames
    """
    nodes_df = pd.DataFrame.from_dict(
        dict(G.nodes(data=True)),
        orient="index"
    )
    nodes_df.index.name = "node"
    nodes_df = nodes_df.sort_index()

    edges_df = pd.DataFrame([
        {"source": u, "target": v, **data}
        for u, v, data in G.edges(data=True)
    ])
    edges_df = edges_df.sort_values(["source", "target"]).reset_index(drop=True)

    return nodes_df, edges_df

def rank_elements(df:object, higher_is_more_important: bool = False,) -> dict:
    """
    Takes a df and ranks the items.
    """

    ranked_data = df.rank(axis=0, method='min', na_option='keep', ascending=higher_is_more_important)
    ranked_data = ranked_data.to_dict()
    return ranked_data

def map_node_values_to_edges(G:nx.Graph, node_values: dict) -> dict:
    """
    Maps node values to edges as the average of the source and target nodes.
    Takes dict and returns dict.
    """
    edge_values = {}
    for u, v in G.edges():
        val_u = node_values[u]
        val_v = node_values[v]
        edge_values[(u, v)] = (val_u + val_v) / 2
    
    return edge_values

def map_node_values_to_blocks(G:nx.Graph, node_values: dict) -> dict:
    """
    Maps node values to blocks as the average across all nodes carrying that block's block_id.
    A block that is just an edge takes the avg. of the nodes. 
    """
    node_block_ids = nx.get_node_attributes(G, 'block_id')
    edge_block_ids = nx.get_edge_attributes(G, 'block_id')

    block_node_values = {}
    for node, block_id in node_block_ids.items():
        try:
            block_node_values.setdefault(block_id, []).append(node_values[node])
        except KeyError:
            pass

    block_values = {
        block_id: sum(vals) / len(vals)
        for block_id, vals in block_node_values.items()
    }

    for (u, v), block_id in edge_block_ids.items():
        if block_id not in block_values:
            block_values[block_id] = (node_values[u] + node_values[v]) / 2

    return block_values

# base directory
def get_dir(filepath:str) -> str:
    dir = os.path.dirname(os.path.abspath(__file__)) # module/dp directory
    dir = os.path.dirname(dir) # get main.py direct
    return os.path.join(dir, filepath)

def compute_disrupted_passengers(edges_with_disruptions: pd.DataFrame,track_nodes: pd.DataFrame,) -> pd.Series:
    """
    Compute the total disrupted passengers as sum of (co_disruption_count x TravelersPerDay) across all co-disrupted stations.
    Returns a Series indexed like edges_with_disruptions.
    """
    travelers_lookup = track_nodes["TravelersPerDay"]

    def _row_total(co_disruption_count):
        disruption_count = {}
        for station, count in co_disruption_count.items():
            disruption_count[station] = disruption_count.get(station, 0) + count
        return sum(
            count * travelers_lookup.get(station, 0)
            for station, count in disruption_count.items()
        )

    return edges_with_disruptions["co_disruption_count"].apply(_row_total)
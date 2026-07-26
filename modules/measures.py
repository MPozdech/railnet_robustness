import pandas as pd
import networkx as nx
import math

def betweenness(infra: nx.Graph, services: nx.Graph, weight: str = None):
    title = f"Weighted Betweenness Centrality (distance = {weight})" if weight else "Unweighted Betweenness Centrality"
    print("running edge betweenness")

    betweenness_infra = nx.edge_betweenness_centrality(infra, normalized=True, weight=weight)
    betweenness_service = nx.edge_betweenness_centrality(services, normalized=True, weight=weight)

    return betweenness_infra, betweenness_service, title

def betweenness_nodes(infra: nx.Graph, services: nx.Graph, weight: str = None):
    title = f"Weighted Node Betweenness Centrality (distance = {weight})" if weight else "Unweighted Node Betweenness Centrality"
    print("running node betweenness")

    betweenness_infra = nx.betweenness_centrality(infra, normalized=True, weight=weight)
    betweenness_service = nx.betweenness_centrality(services, normalized=True, weight=weight)

    return betweenness_infra, betweenness_service, title

def closeness(infra: nx.Graph, services: nx.graph, distance: str = None):
    title = f"Closeness Centrality (distance = {distance})"
    print("running closeness")

    closeness_infra = nx.closeness_centrality(infra, distance=distance)
    closeness_services = nx.closeness_centrality(services, distance=distance)

    return closeness_infra, closeness_services, title

def eigenvector(infra: nx.Graph, services: nx.Graph, initial_importance_attr: str = None, weight_attr: str = None,normalize_weights: bool = True):
    title = f"Eigenvector Centrality (importance = {initial_importance_attr}, weight = {weight_attr})"
    print(f"running eigenvector with initial importance = {initial_importance_attr} & weight = {weight_attr}")

    if initial_importance_attr is not None:
        nstart = nx.get_node_attributes(infra, initial_importance_attr)
        nstart = {node: (val if not math.isnan(val) else 0.0) for node, val in nstart.items()}

        nstart_service = nx.get_node_attributes(services, initial_importance_attr)
        nstart_service = {node: (val if not math.isnan(val) else 0.0) for node, val in nstart_service.items()}
    else:
        nstart = None
        nstart_service = None

    if weight_attr is not None:
        weight = nx.get_edge_attributes(infra, weight_attr)
        weight_service = nx.get_edge_attributes(services, weight_attr)
        if normalize_weights:
            weight = {node: (val if not math.isnan(val) else 0.0) for node, val in weight.items()}
            min_val = min(weight.values())
            max_val = max(weight.values())
            weight = {node: (val - min_val) / (max_val - min_val) for node, val in weight.items()}

            weight_service = {node: (val if not math.isnan(val) else 0.0) for node, val in weight_service.items()}
            min_val = min(weight_service.values())
            max_val = max(weight_service.values())
            weight_service = {node: (val - min_val) / (max_val - min_val) for node, val in weight_service.items()}

        nx.set_edge_attributes(infra, weight, "weight")
        nx.set_edge_attributes(services, weight_service, "weight")
    else:
        weight = None
        weight_service = None

    eigen_infra = nx.eigenvector_centrality(infra, max_iter=10000, nstart=nstart, weight='weight')
    eigen_services = nx.eigenvector_centrality(services, max_iter=10000, nstart=nstart_service, weight='weight')

    return eigen_infra, eigen_services, title

def pagerank(infra: nx.Graph, services: nx.Graph, initial_importance_attr: str = None, weight_attr: str = None):
    title = f"PageRank Centrality (importance = {initial_importance_attr}, weight = {weight_attr})"
    print(f"running pagerank with initial importance = {initial_importance_attr} & weight = {weight_attr}")

    if initial_importance_attr is not None:
        nstart = nx.get_node_attributes(infra, initial_importance_attr)
        nstart = {node: (val if not math.isnan(val) else 0.0) for node, val in nstart.items()}

        nstart_service = nx.get_node_attributes(services, initial_importance_attr)
        nstart_service = {node: (val if not math.isnan(val) else 0.0) for node, val in nstart_service.items()}
    else:
        nstart = None
        nstart_service = None

    if weight_attr is not None:
        weight = nx.get_edge_attributes(infra, weight_attr)
        weight = {node: (val if not math.isnan(val) else 0.0) for node, val in weight.items()}
        min_val = min(weight.values())
        max_val = max(weight.values())
        weight = {node: (val - min_val) / (max_val - min_val) for node, val in weight.items()}

        weight_service = nx.get_edge_attributes(services, weight_attr)
        weight_service = {node: (val if not math.isnan(val) else 0.0) for node, val in weight_service.items()}
        min_val = min(weight_service.values())
        max_val = max(weight_service.values())
        weight_service = {node: (val - min_val) / (max_val - min_val) for node, val in weight_service.items()}

        nx.set_edge_attributes(infra, weight, "normalized_weight")
        nx.set_edge_attributes(services, weight_service, "normalized_weight")
    else:
        weight = None
        weight_service = None

    pagerank_infra      = nx.pagerank(infra,    max_iter=10000, nstart=nstart,         weight='normalized_weight')
    pagerank_services   = nx.pagerank(services, max_iter=10000, nstart=nstart_service, weight='normalized_weight')

    return pagerank_infra, pagerank_services, title
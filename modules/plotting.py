import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import numpy as np
import powerlaw
from scipy.stats import pearsonr
import modules.supporting_functions as sf # type: ignore
from collections import Counter

"""
This module handles every function related to plotting.
Some are generic, some are specific. 
"""

edge_width = 1 # How wide should the plot edges be?
plot_dpi = 200 # How many dots per inch should the plots be?
show_plots = True # Figures are always created and saved; this only controls whether they pop up in the viewer

def _show(fig):
    # Called after savefig in every plotting function: pop the viewer window if true passed
    if show_plots:
        plt.show()
    else:
        plt.close(fig)

def ic_node_labels(G:nx.Graph) -> dict:
    # Helper function to get the IC nodes that should get labeled
    nodes_to_label = {n: n for n, d in G.nodes(data=True) if d.get("ic_station") is True}
    return nodes_to_label

def plot_edge_measure(
    infra: nx.Graph,
    services: nx.Graph,
    pos_segments: dict,
    pos_nodes: dict,
    edge_values_infra: dict,
    edge_values_service: dict,
    title_str: str,
    label_type: str = None,
    print_nodes: bool = False,
    filename: str = 'generic_edge_measure',
    left_subtitle: str = "a) Track graph",
    right_subtitle: str = "b) Service graph",
    save_dir: str = 'measures'
):
    """
    Generic plotting function for any edge-valued graph measure.

    Args:
        infra:               nx.Graph
        services:            nx.Graph
        pos_segments:        dict of infra node positions
        pos_nodes:           dict of service node positions
        node_values_infra:   dict of measure to plot on infra edges
        node_values_service: dict of measure to plot on service edges
        title_str:           string to use as main title
        label_type:          "all" = all labels, "intercity" = ic stations only, "none" = none
        save_dir:            subfolder of figures/ to save into (e.g. 'measures', 'interventions')
        nodesize_scale:      by how much to scale the nodes so they are easier to see on the plot
        filename:            filename
        left/right_subtitle: the subtitles for the plots       
    """

    # Sort edges by value for colormap ordering
    edge_items = sorted(edge_values_infra.items(), key=lambda x: x[1])
    edge_items_service = sorted(edge_values_service.items(), key=lambda x: x[1])
    edgelist_tracks = [edge for edge, _ in edge_items]
    edge_colors_tracks = [val for _, val in edge_items]
    edgelist_service = [edge for edge, _ in edge_items_service]
    edge_colors_service = [val for _, val in edge_items_service]

    vmin = min(min(edge_colors_tracks), min(edge_colors_service))
    vmax = max(max(edge_colors_tracks), max(edge_colors_service))

    # IC label filtering
    nodes_to_label = ic_node_labels(infra) 
    nodes_to_label_services = ic_node_labels(services)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6), sharex=True, sharey=True, dpi=plot_dpi, constrained_layout=True)

    ax1.set_title(left_subtitle)
    edges1 = nx.draw_networkx_edges(
        infra, pos=pos_segments, width=edge_width,
        edgelist=edgelist_tracks, edge_color=edge_colors_tracks,
        edge_cmap=plt.cm.Reds, ax=ax1, edge_vmin=vmin, edge_vmax=vmax,
    )

    ax2.set_title(right_subtitle)
    nx.draw_networkx_edges(
        services, pos=pos_nodes, width=edge_width,
        edgelist=edgelist_service, edge_color=edge_colors_service,
        edge_cmap=plt.cm.Reds, ax=ax2, edge_vmin=vmin, edge_vmax=vmax,
    )

    if print_nodes:
        nx.draw_networkx_nodes(infra, pos=pos_segments, node_size=4, ax=ax1)
        nx.draw_networkx_nodes(services, pos=pos_nodes, node_size=4, ax=ax2)

    if label_type == "intercity":
        nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, labels=nodes_to_label, ax=ax1)
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, labels=nodes_to_label_services, ax=ax2)
    elif label_type == "all":
        nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, ax=ax1)
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, ax=ax2)

    for ax in (ax1, ax2):
        ax.set_xlim(3.5, 7.3)
        ax.set_ylim(50.6, 53.5)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Longitude")
        ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    ax1.set_ylabel("Latitude")
    ax2.tick_params(left=False, labelleft=False)

    cbar = fig.colorbar(edges1, ax=[ax1, ax2], shrink=0.6)
    cbar.set_label("Edge value")
    cbar.ax.yaxis.set_label_position('left')
    fig.suptitle(title_str)
    fig.suptitle(title_str, y=0.99)
    fig.savefig(sf.get_dir(f'figures/{save_dir}/{filename}.jpg'),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def plot_node_measure(
    infra: nx.Graph,
    services: nx.Graph,
    pos_segments: dict,
    pos_nodes: dict,
    node_values_infra: dict,
    node_values_service: dict,
    title_str: str,
    label_type: str = None,
    nodesize_scale: int = 30,
    filename: str = 'generic_node_measure',
    left_subtitle: str = "a) Track graph",
    right_subtitle: str = "b) Service graph"
):
    """
    Generic plotting function for any node-valued graph measure.

    Args:
        infra:               nx.Graph
        services:            nx.Graph
        pos_segments:        dict of infra node positions
        pos_nodes:           dict of service node positions
        node_values_infra:   dict of measure to plot on infra nodes
        node_values_service: dict of measure to plot on service nodes
        stations:            dataFrame with IC station for label plotting
        title_str:           string to use as main title
        label_type:          "all" = all labels, "intercity" = ic stations only, "none" = none
        nodesize_scale:      by how much to scale the nodes so they are easier to see on the plot
        filename:            filename
        left/right_subtitle: the subtitles for the plots
    """

    # Sort nodes by value for colormap ordering
    edge_items = sorted(node_values_infra.items(), key=lambda x: x[1])
    edge_items_service = sorted(node_values_service.items(), key=lambda x: x[1])
    edgelist_tracks = [edge for edge, _ in edge_items]
    edge_colors_tracks = [val * nodesize_scale for _, val in edge_items]
    edgelist_service = [edge for edge, _ in edge_items_service]
    edge_colors_service = [val * nodesize_scale for _, val in edge_items_service]

    vmin = min(min(edge_colors_tracks), min(edge_colors_service))
    vmax = max(max(edge_colors_tracks), max(edge_colors_service))

    # IC label filtering
    nodes_to_label = ic_node_labels(infra)
    nodes_to_label_services = ic_node_labels(services)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6), sharex=True, sharey=True, dpi=plot_dpi, constrained_layout=True)

    ax1.set_title(left_subtitle)
    nodes1 = nx.draw_networkx_nodes(infra, 
                           pos=pos_segments,
                           nodelist=edgelist_tracks,
                           node_size=edge_colors_tracks,
                           node_color=edge_colors_tracks,
                           cmap = plt.cm.Reds,
                           edgecolors='k',
                           linewidths=0.5,
                           vmin = vmin,
                           vmax = vmax, 
                           ax=ax1)
    #nodes1.set_edgecolor('r')
    edges1 = nx.draw_networkx_edges(
        infra, 
        pos=pos_segments, 
        width=edge_width,
        #edgelist=edgelist_tracks, 
        #edge_color=edge_colors_tracks,
        #edge_cmap=plt.cm.Reds, 
        ax=ax1, 
        #edge_vmin=vmin, 
        #edge_vmax=vmax,
    )

    ax2.set_title(right_subtitle)
    nodes2 = nx.draw_networkx_nodes(services, 
                           pos=pos_nodes, 
                           nodelist=edgelist_service, 
                           node_size=edge_colors_service,
                           node_color=edge_colors_service,
                           edgecolors='k',
                           linewidths=0.5,
                           cmap=plt.cm.Reds,
                           vmin=vmin,
                           vmax = vmax,
                           ax=ax2)
    #nodes2.set_edgecolor('r')
    nx.draw_networkx_edges(
        services, pos=pos_nodes, 
        width=edge_width,
        #edge_cmap=plt.cm.Reds, 
        ax=ax2, 
        #edge_vmin=vmin, 
        #edge_vmax=vmax
    )

    if label_type == "intercity":
        nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, labels=nodes_to_label, ax=ax1)
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, labels=nodes_to_label_services, ax=ax2)
    elif label_type == "all":
        nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, ax=ax1)
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, ax=ax2)

    for ax in (ax1, ax2):
        ax.set_xlim(3.5, 7.3)
        ax.set_ylim(50.6, 53.5)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Longitude")
        ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    ax1.set_ylabel("Latitude")
    ax2.tick_params(left=False, labelleft=False)

    cbar = fig.colorbar(nodes1, ax=[ax1, ax2], shrink=0.6)
    cbar.set_label("Node value")
    cbar.ax.yaxis.set_label_position('left')
    fig.suptitle(title_str)
    fig.suptitle(title_str, y=0.99)
    fig.savefig(sf.get_dir(f'figures/measures/{filename}.jpg'),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def plot_measure(
    G: nx.Graph,
    pos: dict,
    measure_type: str,
    measure_values: dict,
    title_str: str,
    colorbar_label: str = "Value",
    label_type: str = None,
    print_nodes: bool = False,
    nodesize_scale: int = 30,
    cmap=plt.cm.Reds,
    filename: str = 'generic_measure'
):
    """
    Generic plotting function for a single node- or edge-valued graph measure
    on one graph.

    Args:
        G:               nx.Graph
        pos:             dict of node positions
        measure_type:    "node" or "edge" - which kind of measure_values this is
        measure_values:  dict of measure values, keyed by node (measure_type="node")
                         or by (u, v) edge tuple (measure_type="edge")
        title_str:       string to use as title
        colorbar_label:  label for the colorbar
        label_type:      "all" = all labels, "ic" = ic stations only, None = none
        print_nodes:     whether to draw nodes (only used when measure_type="edge")
        nodesize_scale:  multiplier for node size/color (only used when measure_type="node")
        cmap:            matplotlib colormap to use
    """
    if measure_type not in ("node", "edge"):
        raise ValueError(f"measure_type must be 'node' or 'edge', got {measure_type!r}")

    nodes_to_label = ic_node_labels(G)

    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    ax.set_title(title_str)

    if measure_type == "edge":
        edge_items = sorted(measure_values.items(), key=lambda x: x[1])
        edgelist = [edge for edge, _ in edge_items]
        edge_colors = [val for _, val in edge_items]

        drawn = nx.draw_networkx_edges(
            G, pos=pos, width=edge_width,
            edgelist=edgelist, edge_color=edge_colors,
            edge_cmap=cmap, ax=ax,
            edge_vmin=min(edge_colors), edge_vmax=max(edge_colors),
        )
        if print_nodes:
            nx.draw_networkx_nodes(G, pos=pos, node_size=2, ax=ax)
    else:
        node_items = sorted(measure_values.items(), key=lambda x: x[1])
        nodelist = [node for node, _ in node_items]
        node_colors = [val * nodesize_scale for _, val in node_items]

        drawn = nx.draw_networkx_nodes(
            G, pos=pos,
            nodelist=nodelist,
            node_size=node_colors,
            node_color=node_colors,
            cmap=cmap,
            edgecolors='k',
            linewidths=0.5,
            vmin=min(node_colors),
            vmax=max(node_colors),
            ax=ax,
        )
        nx.draw_networkx_edges(G, pos=pos, width=edge_width, ax=ax)

    if label_type == "ic":
        nx.draw_networkx_labels(G, pos=pos, font_size=8, labels=nodes_to_label, ax=ax)
    elif label_type == "all":
        nx.draw_networkx_labels(G, pos=pos, font_size=8, ax=ax)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    cbar = fig.colorbar(drawn, ax=ax, shrink=0.6)
    cbar.set_label(colorbar_label)
    cbar.ax.yaxis.set_label_position('left')

    fig.savefig(sf.get_dir(f"figures/measures/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def ipv_services(services: nx.Graph, pos_nodes: dict, label_type: str, print_nodes: bool = False, show_no_ipv: bool = False):
    # Plotting priority order
    TYPE_PRIORITY = [
        "Bus",
        "OV-bus ipv trein",
        "Metro ipv trein",
        "Snelbus ipv trein",
        "Stopbus ipv trein",
        "Taxibus ipv trein",
        "Belbus ipv trein",
    ]

    def dominant_type(service_type_breakdown: dict) -> str | None:
        # Get the most frequent type per edge
        if not isinstance(service_type_breakdown, dict) or not service_type_breakdown:
            return None
        present_types = service_type_breakdown.keys()
        for t in TYPE_PRIORITY:
            if t in present_types:
                return t
        return next(iter(present_types)) 

    # Colors
    type_colors = {
        "Bus":                "#e6194b",
        "Metro ipv trein":    "#ffe119",
        "OV-bus ipv trein":   "#3cb44b",
        "Snelbus ipv trein":  "#1947ee",
        "Stopbus ipv trein":  "#911eb4",
        "Taxibus ipv trein":  "#42d4f4",
        "Belbus ipv trein":   "#f58231",
        "No IPV service":     "#000000",
    }

    # Assign each edge a color from graph edge attributes
    edge_list   = []
    edge_colors = []
    edge_types  = []

    for u, v, data in services.edges(data=True):
        breakdown = data.get("ipv_service_types")
        stype = dominant_type(breakdown)

        if stype:
            edge_list.append((u, v))
            edge_colors.append(type_colors.get(stype, "#888888"))
            edge_types.append(stype)
        elif show_no_ipv:
            edge_list.append((u, v))
            edge_colors.append(type_colors["No IPV service"])
            edge_types.append("No IPV service")

    # Plot
    nodes_to_label = ic_node_labels(services)
    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    nx.draw_networkx_edges(
        services,
        pos=pos_nodes,
        edgelist=edge_list,
        edge_color=edge_colors,
        width=edge_width,
        ax=ax,
    )
    if print_nodes:
        nx.draw_networkx_nodes(services, pos=pos_nodes, node_size=1, ax=ax,node_color='k')
    if label_type == "ic":
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, labels=nodes_to_label, ax=ax)
    elif label_type == "all":
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, ax=ax)

    #  Legend
    observed_types = sorted(set(edge_types))
    legend_handles = [
        mpatches.Patch(color=type_colors.get(t, "#888888"), label=t)
        for t in observed_types
    ]
    ax.legend(
        handles=legend_handles,
        title="Service Replacement Type",
        loc="lower right",
        fontsize=7,
        title_fontsize=8,
        framealpha=0.9,
    )
    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.title("Train Replacement Services, 2023~25")
    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/rdt/ipv_services.jpg"),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def demand_flow_comparison(
        infra: nx.Graph, 
        infra_model: nx.Graph, 
        services: nx.Graph, 
        pos_segments: dict, 
        pos_nodes: dict,
        label_type: str,
        plot_nodes: bool = False):
    """
    Plots the the avg duration of a disruption from the RDT database onto the graphs.
    Assumes any disruption on SPR segment also influenced IC segment but not the other way.

    Args:
        infra: The track graph with flows only as derived from the NS JSON.
        infra_extrapolated: The track graph with ALL flows derived from the demand assignment.
        pos_segments: Dict of node names derived from segment data and their coordinates.
        stations: DataFrame that states if a station is IC or not.
        label_type: None, 'ic', or 'all'
        plot_nodes: show nodes in plot or not
    """

    # Get flow 
    ns_only = {
        (u, v): data["real_flow"]
        for u, v, data in infra.edges(data=True)
        if data.get("real_flow") not in [None, 0]
    }

    infra_model_values = {
        (u, v): data["flow"]
        for u, v, data in infra_model.edges(data=True)
        if data.get("flow") not in [None, 0]
    }

    mixed = {
        (u, v): data["flow"]
        for u, v, data in infra.edges(data=True)
        if data.get("flow") not in [None, 0]
    }

    service_model = {
        (u, v): data["flow"]
        for u, v, data in services.edges(data=True)
        if data.get("flow") not in [None, 0]
    }

    # Sort values for colorbar input
    edge_items_ns_only = sorted(
        ns_only.items(),
        key=lambda x: x[1])
    edge_items_infra_model = sorted(
        infra_model_values.items(),
        key=lambda x: x[1])
        # Sort values for colorbar input
    edge_items_mixed = sorted(
        mixed.items(),
        key=lambda x: x[1])
    edge_items_service = sorted(
        service_model.items(),
        key=lambda x: x[1])
    
    edgelist_ns = [edge for edge, val in edge_items_ns_only]
    edge_colors_ns = [val for edge, val in edge_items_ns_only]
    edgelist_infra_model = [edge for edge, val in edge_items_infra_model]
    edge_colors_infra_model = [val for edge, val in edge_items_infra_model]
    edgelist_mixed = [edge for edge, val in edge_items_mixed]
    edge_colors_mixed = [val for edge, val in edge_items_mixed]
    edgelist_service = [edge for edge, val in edge_items_service]
    edge_colors_service = [val for edge, val in edge_items_service]

    # Colorbar normalization
    vmin = min(min(edge_colors_ns), min(edge_colors_infra_model), min(edge_colors_mixed), min(edge_colors_service))
    vmax = max(max(edge_colors_ns), max(edge_colors_infra_model), max(edge_colors_mixed), max(edge_colors_service))

    # Attach IC station attributes so only IC stations have their labels printed
    nodes_to_label          = ic_node_labels(infra)
    nodes_to_label_services = ic_node_labels(services)

    fig, ((ax1, ax2),(ax3,ax4)) = plt.subplots(2, 2, figsize=(12,6), sharex=True, sharey=True, dpi=plot_dpi)

    ax1.set_title("a) Only NS flow (to_ + from_travelers)")
    edges1 = nx.draw_networkx_edges(
        infra,
        pos=pos_segments,
        width=edge_width,
        edgelist=edgelist_ns,
        edge_color=edge_colors_ns,
        edge_cmap=plt.cm.Reds,
        ax=ax1,
        edge_vmin=vmin,
        edge_vmax=vmax
    )

    ax2.set_title("b) Only modeled flow")
    edges2 = nx.draw_networkx_edges(
        infra_model,
        pos=pos_segments,
        width=edge_width,
        edgelist=edgelist_infra_model,
        edge_color=edge_colors_infra_model,
        edge_cmap=plt.cm.Reds,
        ax=ax2,
        edge_vmin=vmin,
        edge_vmax=vmax
    )

    ax3.set_title("c) NS flow + modeled flow")
    edges3 = nx.draw_networkx_edges(
        infra,
        pos=pos_segments,
        width=edge_width,
        edgelist=edgelist_mixed,
        edge_color=edge_colors_mixed,
        edge_cmap=plt.cm.Reds,
        ax=ax3,
        edge_vmin=vmin,
        edge_vmax=vmax
    )

    ax4.set_title("d) Modeled flow on service edges")
    edges4 = nx.draw_networkx_edges(
        services,
        pos=pos_nodes,
        width=edge_width,
        edgelist=edgelist_service,
        edge_color=edge_colors_service,
        edge_cmap=plt.cm.Reds,
        ax=ax4,
        edge_vmin=vmin,
        edge_vmax=vmax
    )
    
    if plot_nodes:
        nodes1 = nx.draw_networkx_nodes(
            infra,
            pos=pos_segments,
            node_size=2,
            ax=ax1
        )
        nodes2 = nx.draw_networkx_nodes(
            infra_model,
            pos=pos_segments,
            node_size=2,
            ax=ax2
        )
        nodes3 = nx.draw_networkx_nodes(
            infra,
            pos=pos_segments,
            node_size=2,
            ax=ax3
        )
        nodes4 = nx.draw_networkx_nodes(
            services,
            pos=pos_nodes,
            node_size=2,
            ax=ax4
        )

    if label_type == "intercity":
        for ax in [ax1, ax2, ax3]:
            labels1 = nx.draw_networkx_labels(infra,pos=pos_segments,font_size=8,labels=nodes_to_label,ax=ax)
        labels2 = nx.draw_networkx_labels(services,pos=pos_segments,font_size=8,labels=nodes_to_label_services,ax=ax4)
    elif label_type == "all":
        for ax in [ax1, ax2, ax3]:
            labels1 = nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, ax=ax)
        labels2 = nx.draw_networkx_labels(services,pos=pos_nodes,font_size=8,ax=ax4)
    for ax in (ax1, ax2, ax3, ax4):
        ax.set_aspect("equal", adjustable="box")
        ax.set_ylabel("Latitude")
        ax.set_ylim(50.6, 53.5)
        ax.tick_params(left=True, labelleft=True, bottom=True, labelbottom=True)
        ax.set_xlabel("Longitude")
        ax.set_xlim(3.5, 7.3)

    cbar = fig.colorbar(edges1, ax=[ax1,ax2,ax3,ax4], label="Average Passengers per-day [pax/day]",shrink=0.8)
    cbar.ax.yaxis.set_label_position('left')
    fig.suptitle("Passenger Flows Across Track Edges")
    fig.savefig(sf.get_dir(f"figures/demand/demand_flows.jpg"),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def plot_flow_diff(
    G_base: nx.Graph,
    G_new: nx.Graph,
    pos: dict,
    title_str: str = "Flow Difference",
    label_type: str = None,
    edge_width_scale: float = 5.0,
    no_diff_width: float = 0.5,
    cutoff: int = 100,
    edge_attribute:str='flow',
    filename: str = 'generic_flow_difference',
    show_report:bool = False,
):
    """
    Plots edge-level flow differences between two graphs.
    Edges with increased flow are green, decreased are red, unchanged are black.
    Edge width scales with the magnitude of the difference.

    Args:
        G_base:           baseline nx.Graph (with 'flow' edge attribute)
        G_new:            new nx.Graph (with 'flow' edge attribute)
        pos:              dict of node positions
        title_str:        string to use as title
        label_type:       "all", "ic", or None
        edge_width_scale: multiplier for difference-based edge width
        no_diff_width:    width for edges with no difference
        cutoff:           how large of a difference required to plot differences
    """
    increased_edges, increased_widths = [], []
    decreased_edges, decreased_widths = [], []
    unchanged_edges = []

    for u, v, d in G_base.edges(data=True):
        base_flow = d.get(edge_attribute, 0)
        new_flow  = G_new[u][v].get(edge_attribute, 0) if G_new.has_edge(u, v) else 0
        diff = new_flow - base_flow

        if diff > cutoff:
            increased_edges.append((u, v))
            increased_widths.append(diff)
        elif diff < -cutoff:
            decreased_edges.append((u, v))
            decreased_widths.append(abs(diff))
        else:
            unchanged_edges.append((u, v))

    for u, v, d in G_new.edges(data=True):
        if not G_base.has_edge(u, v):
            new_flow = d.get(edge_attribute, 0)
            if new_flow > 0:
                increased_edges.append((u, v))
                increased_widths.append(new_flow)
            else:
                unchanged_edges.append((u, v))

    flow_diff_report = {}
    for u, v in increased_edges:
        base_flow = G_base[u][v].get("flow", 0) if G_base.has_edge(u, v) else 0
        new_flow  = G_new[u][v].get("flow", 0)
        flow_diff_report[(u, v)] = round(new_flow - base_flow, 2)
    for u, v in decreased_edges:
        base_flow = G_base[u][v].get("flow", 0)
        new_flow  = G_new[u][v].get("flow", 0) if G_new.has_edge(u, v) else 0
        flow_diff_report[(u, v)] = round(new_flow - base_flow, 2)

    if show_report:
        for k, v in sorted(flow_diff_report.items(), key=lambda x: x[1], reverse=True):
            print(f"{k}: {v}")

    # Normalise widths relative to the largest difference
    max_diff = max(increased_widths + decreased_widths, default=1)
    increased_widths = [w / max_diff * edge_width_scale for w in increased_widths]
    decreased_widths = [w / max_diff * edge_width_scale for w in decreased_widths]

    fig, ax = plt.subplots(1, 1, figsize=(7, 8), dpi=plot_dpi)

    # Nodes
    nx.draw_networkx_nodes(G_new, pos=pos,
                           edgecolors="k",
                           linewidths=0.5,
                           node_size=8,
                           ax=ax)

    # Unchanged edges
    nx.draw_networkx_edges(G_new, pos=pos,
                            edgelist=unchanged_edges, edge_color="black",
                            width=no_diff_width, ax=ax)
    if increased_edges:
        nx.draw_networkx_edges(G_new, pos=pos,
                            edgelist=increased_edges, edge_color="green",
                            width=increased_widths, ax=ax)
    if decreased_edges:
        nx.draw_networkx_edges(G_new, pos=pos,
                            edgelist=decreased_edges, edge_color="red",
                            width=decreased_widths, ax=ax)
    # Labels
    if label_type == "ic":
        nx.draw_networkx_labels(G_base, pos=pos, font_size=8,
                                labels=ic_node_labels(G_base), ax=ax)
    elif label_type == "all":
        nx.draw_networkx_labels(G_base, pos=pos, font_size=8, ax=ax)

    # Legend
    legend_elements = [
        Line2D([0], [0], color="green", linewidth=2, label="Increased flow"),
        Line2D([0], [0], color="red",   linewidth=2, label="Decreased flow"),
        Line2D([0], [0], color="black", linewidth=1, label="No change"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    fig.tight_layout()
    fig.suptitle(title_str)
    fig.savefig(sf.get_dir(f"figures/interventions/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_disruption_heatmap(
    infra: nx.Graph,
    services: nx.Graph,
    pos_segments: dict,
    pos_nodes: dict,
    edges_with_disruptions: pd.DataFrame,
    target1: str,
    target2: str,
    figsize: tuple = (14, 10),
    cmap: str = "YlOrRd",
    print_output:bool = False
):
    # Retrieve disruption_count for target edge
    try:
        row = edges_with_disruptions.loc[[(target1,target2)]]
    except:
        row = edges_with_disruptions.loc[[(target2,target1)]]

    disruption_count = {}
    if not row.empty:
        for d in row["co_disruption_count"]:
            for station, count in d.items():
                disruption_count[station] = disruption_count.get(station, 0) + count

    # Build per-node color values
    nodes = list(infra.nodes())
    counts = np.array([disruption_count.get(n, 0) for n in nodes])
    sorted_dict = {key: value for key, 
        value in sorted(disruption_count.items(), 
                        key=lambda item: item[1])}
    if print_output: print(sorted_dict)

    max_count = counts.max() if counts.max() > 0 else 1
    norm = mcolors.Normalize(vmin=0, vmax=max_count)
    colormap = plt.cm.get_cmap(cmap)
    node_colors = [colormap(norm(c)) for c in counts]

    # Set colors
    all_edges = list(infra.edges())
    target_set = {(target1, target2), (target2, target1)}
    edge_colors = ["#e63946" if e in target_set else "#cccccc" for e in all_edges]
    edge_widths = [3.5 if e in target_set else edge_width for e in all_edges]

    # Plot
    fig, ax = plt.subplots(figsize=figsize)

    affected_nodes = [n for n in nodes if disruption_count.get(n, 0) > 0]
    unaffected_nodes = [n for n in nodes if disruption_count.get(n, 0) == 0]

    nx.draw_networkx_edges(
        infra, pos_segments,
        edge_color=edge_colors,
        width=edge_widths,
        alpha=0.7,
        ax=ax,
    )

    # Highlight targeted service edge
    nx.draw_networkx_edges(
        services, pos_nodes,
        edge_color="#e63946",
        edgelist={(target1,target2)},
        width=3.5,
        alpha=0.7,
        ax=ax
    )

    # Unaffected: small black dots, no label
    nx.draw_networkx_nodes(
        infra, pos_segments,
        nodelist=unaffected_nodes,
        node_color="black",
        node_size=5,
        ax=ax,
    )

    # Affected: full colormap, larger, with labels
    affected_colors = [colormap(norm(disruption_count.get(n, 0))) for n in affected_nodes]
    nx.draw_networkx_nodes(
        infra, pos_segments,
        nodelist=affected_nodes,
        node_color=affected_colors,
        node_size=100,
        ax=ax,
    )
    nx.draw_networkx_labels(
        infra, pos_segments,
        labels={n: n for n in affected_nodes},  # only label affected nodes
        font_size=6,
        font_color="black",
        ax=ax,
    )

    sm = plt.cm.ScalarMappable(cmap=colormap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("Co-disruption count", fontsize=10)
    cbar.ax.yaxis.set_label_position('left')

    n_disruptions = row["n_disruptions"].sum() if not row.empty else 0
    ax.set_title(
        f"Disruption heatmap for edge {target1} - {target2} ({int(n_disruptions)} disruptions)",
        fontsize=13, fontweight="bold", pad=14,
    )
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)
    plt.tight_layout()
    fig.savefig(sf.get_dir(f"figures/rdt/codisruption_heatmap_{target1}_{target2}.jpg"),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def plot_correlations(df: object, title: str = 'Infra correlations',filename:str='generic_correlation_plot',metric_groups: dict[str, list[str]] = None,figsize: tuple = (14, 6)):
    """
    Scatter plot of measure-metric correlation coefficients (significant cells only).

    metric_groups: define in a dict which metrics to plot
    """
    # Filter to the requested metrics BEFORE the averages below, so the legend's avg. coefficients only consider the metrics actually shown
    if metric_groups is not None:
        wanted = [name for names in metric_groups.values() for name in names]
        selected = []
        for name in wanted:
            for row_label in df.index:
                if row_label not in selected and (row_label == name or str(row_label).startswith(name + '_')):
                    selected.append(row_label)
        df = df.loc[selected]

    fig, ax = plt.subplots(figsize=figsize)
    colors = ['#4C72B0', '#DD8452', '#55A868', '#C44E52', '#8172B2']
    label_names = ['Betweenness (travel time)', 'Eigenvector (none)', 'Eigenvector (flow)', 'Closeness (travel time)', 'Pagerank (none)']

    # Pre-compute avg x_val per column, only where y_val < 0.05.
    avg_per_col = {}
    for col in df.columns:
        vals = [
            cell[0] for cell in df[col]
            if isinstance(cell, (tuple, list)) and cell[0] is not None and cell[1] is not None and cell[1] < 0.05
        ]
        pos_vals = [v for v in vals if v > 0]
        neg_vals = [v for v in vals if v < 0]
        avg_per_col[col] = (
            np.nanmean(pos_vals) if pos_vals else None,
            np.nanmean(neg_vals) if neg_vals else None
        )

    # Build labels with avg correlation
    labels_with_avg = []
    for col_idx, col in enumerate(df.columns):
        avg_pos, avg_neg = avg_per_col[col]
        pos_str = f"+{avg_pos:.2f}" if avg_pos is not None else "n/a"
        neg_str = f"{avg_neg:.2f}" if avg_neg is not None else "n/a"
        if avg_pos is not None or avg_neg is not None:
            labels_with_avg.append(f"{label_names[col_idx]} , avg. coef = ({pos_str}, {neg_str})")
        else:
            labels_with_avg.append(f"{label_names[col_idx]} , no sig. values")

    for col_idx, col in enumerate(df.columns):
        for row_idx, row_label in enumerate(df.index):
            cell = df.loc[row_label, col]
            if not isinstance(cell, (tuple, list)):
                # NaN (fresh frame) or None (reloaded) for skipped-metric rows
                continue
            x_val, y_val = cell
            if x_val is None or y_val is None:
                continue
            if y_val < 0.05:
                ax.scatter(
                    row_idx,
                    x_val,
                    color=colors[col_idx % len(colors)],
                    label=labels_with_avg[col_idx],
                    s=60,
                    alpha=0.8,
                    zorder=3
                )

    ax.set_xticks(range(len(df.index)))
    ax.set_xticklabels(df.index, rotation=45, ha='right', fontsize=9)
    ax.set_xlabel("Metric")
    ax.set_ylabel("Correlation coefficient")
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), title="Measure", loc='best')
    fig.savefig(sf.get_dir(f"figures/correlations/{filename}.jpg"),bbox_inches="tight",dpi=plot_dpi)
    plt.tight_layout()
    _show(fig)

def plot_rdt_edge_metric(services: nx.Graph,pos_nodes: dict,edge_attribute: str,title: str,colorbar_label: str,filename: str,label_type: str,print_nodes: bool = False,cmap=plt.cm.Reds):
    """Plots a numeric edge attribute from the service graph as a colorbar plot.

    Args:
        services: The service graph with edge attributes.
        pos_nodes: Dict of node names and their geographic coordinates.
        edge_attribute: The edge attribute key to read and visualize.
        title: Title of the plot.
        colorbar_label: Label for the colorbar.
        label_type: Can either print "all" labels, only "ic" station labels, or None.
        print_nodes: Whether to draw nodes.
        cmap: Matplotlib colormap to use.
        filename: filename
    """
    # Extract edge attribute values, skipping edges where the attribute is missing
    edge_metric = {
        (u, v): data[edge_attribute]
        for u, v, data in services.edges(data=True)
        if edge_attribute in data and pd.notna(data[edge_attribute])
    }

    if not edge_metric:
        raise ValueError(f"No edges found with attribute '{edge_attribute}'.")

    # Sort for colormap consistency
    edge_items = sorted(edge_metric.items(), key=lambda x: x[1])
    edgelist = [edge for edge, val in edge_items]
    edge_colors = [val for edge, val in edge_items]

    vmin = min(edge_colors)
    vmax = max(edge_colors)

    nodes_to_label_services = ic_node_labels(services)

    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    ax.set_title(title)

    edges_drawn = nx.draw_networkx_edges(
        services,
        pos=pos_nodes,
        width=edge_width,
        edgelist=edgelist,
        edge_color=edge_colors,
        edge_cmap=cmap,
        ax=ax,
        edge_vmin=vmin,
        edge_vmax=vmax,
    )

    if print_nodes:
        nx.draw_networkx_nodes(services, pos=pos_nodes, node_size=2, ax=ax)

    if label_type == "ic":
        nx.draw_networkx_labels(
            services,
            pos=pos_nodes,
            font_size=8,
            labels=nodes_to_label_services,
            ax=ax,
        )
    elif label_type == "all":
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, ax=ax)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    cbar = fig.colorbar(edges_drawn, ax=ax, shrink=0.6)
    cbar.set_label(colorbar_label)
    cbar.ax.yaxis.set_label_position("left")

    fig.savefig(sf.get_dir(f"figures/rdt/{filename}.jpg"),bbox_inches="tight",dpi=plot_dpi)
    _show(fig)

def plot_disrupted_pax_minutes(
    services: nx.Graph,
    pos_nodes: dict,
    title: str = "Disrupted passenger-minutes from 2023 to 2025",
    colorbar_label: str = "pax-min",
    filename: str = "disrupted_pax_minutes",
    label_type: str = None,
    flow_attribute: str = "flow",
    duration_attribute: str = "total_duration",
    print_nodes: bool = False,
    cmap=plt.cm.Reds,
):
    """Plots disrupted passenger-minutes per service edge as a colorbar plot.

    For each edge, disrupted pax-minutes = (passenger flow across the edge) x (total minutes that edge was disrupted)

    Args:
        services: The service graph, with per-edge flow and total_duration attributes.
        pos_nodes: Dict of node names and their geographic coordinates.
        title: Title of the plot.
        colorbar_label: Label for the colorbar.
        filename: Output filename (no extension); saved under figures/rdt/.
        label_type: Can either print "all" labels, only "ic" station labels, or None.
        flow_attribute: The edge attribute holding passenger flow (default 'flow').
        duration_attribute: The edge attribute holding total disrupted minutes (default 'total_duration').
        print_nodes: Whether to draw nodes.
        cmap: Matplotlib colormap to use (default: plt.cm.Reds).
    """
    # pax-min per edge = flow x total disrupted duration. Edges with no duration (never disrupted) get 0
    edge_metric = {}
    for u, v, data in services.edges(data=True):
        flow = data.get(flow_attribute)
        if flow is None or pd.isna(flow):
            continue
        duration = data.get(duration_attribute)
        if duration is None or pd.isna(duration):
            duration = 0.0
        edge_metric[(u, v)] = flow * duration

    if not edge_metric:
        raise ValueError(f"No edges found with attribute '{flow_attribute}'.")

    # Sort for colormap consistency
    edge_items = sorted(edge_metric.items(), key=lambda x: x[1])
    edgelist = [edge for edge, val in edge_items]
    edge_colors = [val for edge, val in edge_items]

    vmin = min(edge_colors)
    vmax = max(edge_colors)

    nodes_to_label_services = ic_node_labels(services)

    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    ax.set_title(title)

    edges_drawn = nx.draw_networkx_edges(
        services,
        pos=pos_nodes,
        width=edge_width,
        edgelist=edgelist,
        edge_color=edge_colors,
        edge_cmap=cmap,
        ax=ax,
        edge_vmin=vmin,
        edge_vmax=vmax,
    )

    if print_nodes:
        nx.draw_networkx_nodes(services, pos=pos_nodes, node_size=2, ax=ax)

    if label_type == "ic":
        nx.draw_networkx_labels(
            services,
            pos=pos_nodes,
            font_size=8,
            labels=nodes_to_label_services,
            ax=ax,
        )
    elif label_type == "all":
        nx.draw_networkx_labels(services, pos=pos_nodes, font_size=8, ax=ax)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    cbar = fig.colorbar(edges_drawn, ax=ax, shrink=0.6)
    cbar.set_label(colorbar_label)
    cbar.ax.yaxis.set_label_position("left")

    fig.savefig(sf.get_dir(f"figures/rdt/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_ipv_coverage_by_duration(
    disruption_replacements: pd.DataFrame,
    bins: list[int] = [30, 60, 90, 120],
    title: str = 'IPV replacement coverage by disruption duration',
    filename: str = 'ipv_coverage_by_duration',
    color: str = 'steelblue',
):
    """
    Line chart of the share of disruptions that received at least one IPV
    replacement service, bucketed by disruption duration.

    Args:
        disruption_replacements : DataFrame with 'duration_minutes' and 'replacement_services'
        bins     : ascending list of duration-bin edges in minutes. 
    """
    if len(bins) < 2:
        raise ValueError("bins must contain at least two edges to form one bucket.")

    df = disruption_replacements[['duration_minutes', 'replacement_services']].copy()
    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce')
    df['replacement_services'] = pd.to_numeric(df['replacement_services'], errors='coerce').fillna(0)
    df = df.dropna(subset=['duration_minutes'])

    # Fold everything at/beyond the last defined edge into one overflow bucket
    n_regular = len(bins) - 1
    max_duration = df['duration_minutes'].max() if not df.empty else None
    has_overflow = max_duration is not None and max_duration >= bins[-1]
    bin_edges = list(bins) + [max_duration + 1] if has_overflow else list(bins)  # +1 so right=False still includes the true max

    # Assign each disruption to a bucket
    labels = [f"{bin_edges[i]}-{bin_edges[i + 1]}" for i in range(len(bin_edges) - 1)]
    df['bucket'] = pd.cut(df['duration_minutes'], bins=bin_edges, right=False, labels=labels)

    # Per-bucket: total disruptions and how many had >= 1 IPV replacement
    grouped = df.groupby('bucket', observed=False)
    totals = grouped.size()
    with_ipv = grouped['replacement_services'].apply(lambda s: (s > 0).sum())
    pct = (with_ipv / totals * 100).where(totals > 0)  # NaN where the bucket is empty

    y = pct.reindex(labels).values

    # X positions = the LEFT edge of each bucket, in hours
    edges_h = np.asarray(bin_edges, dtype=float) / 60.0
    x_regular = edges_h[:n_regular]
    if has_overflow:
        overflow_x = edges_h[n_regular]
        x = np.append(x_regular, overflow_x)
    else:
        x = x_regular

    n_buckets = len(labels)
    fig_w = min(14, max(7, n_buckets * 0.42))
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=plot_dpi)

    ax.plot(x, y, color=color, linewidth=1.6, marker='o', markersize=6,
            markerfacecolor='white', markeredgecolor=color, markeredgewidth=1.4, zorder=3)

    # Annotate each point, alternating above / below the line
    for i, (xi, yi) in enumerate(zip(x, y)):
        if np.isnan(yi):
            continue
        above = (i % 2 == 0)
        ax.annotate(
            f"{yi:.1f}%",
            xy=(xi, yi),
            xytext=(0, 9 if above else -9), textcoords="offset points",
            ha='center', va='bottom' if above else 'top',
            fontsize=7, color=color, zorder=4,
        )

    # Ticks are placed only at data points that land on a whole hour
    is_whole_hour = np.isclose(x_regular, np.round(x_regular), atol=1e-6)
    whole_positions = x_regular[is_whole_hour]
    max_ticks = 12
    if len(whole_positions) > max_ticks:
        step = int(np.ceil(len(whole_positions) / max_ticks))
        thinned = whole_positions[::step]
        if whole_positions[-1] not in thinned:  # keep the true end of the regular range
            thinned = np.append(thinned, whole_positions[-1])
        whole_positions = thinned

    tick_locs = list(whole_positions)
    tick_labels = [f"{int(round(t))}" for t in tick_locs]
    if has_overflow:
        tick_locs.append(overflow_x)
        tick_labels.append(f"{int(round(edges_h[n_regular]))}h+")
    ax.set_xticks(tick_locs)
    ax.set_xticklabels(tick_labels)

    xpad = (x[-1] - edges_h[0]) * 0.04
    ax.set_xlim(edges_h[0] - xpad, x[-1] + xpad)

    ax.set_xlabel("Disruption duration [hours]", fontsize=10)
    ax.set_ylabel("Disruptions with IPV services provided [%]", fontsize=10)
    ax.set_title(title, fontsize=11, pad=8)
    ax.tick_params(axis="both", labelsize=8)

    # Headroom above and below for the alternating annotations
    finite = y[~np.isnan(y)]
    if finite.size:
        top = finite.max() * 1.35
        ax.set_ylim(-finite.max() * 0.22, top)
        ax.set_yticks([t for t in ax.get_yticks() if t >= 0])  # hide the negative padding ticks
        ax.set_ylim(-finite.max() * 0.22, top)
    else:
        ax.set_ylim(0, 1)

    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5, zorder=0)

    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/rdt/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_metric_boxplots(
    dfs: list[pd.DataFrame],
    group_labels: list[str],
    title: str = 'Metric distributions per disruption',
    scaling: str = 'zscore',  # 'zscore' | 'minmax' | 'none'
    figsize: tuple = (16, 16),
    filename: str = 'generic_metric_boxplot',
    metric_groups: dict[str, list[str]] = None,
    ):
    """
    Boxplots of every numeric impact metric, side-by-side per group (e.g. no_alt / ipv / ov).
    """
    # Identifier/label columns
    EXCLUDED_COLS = {
        'source', 'target', 'node', 'graph_connected', 'disconnected_nodes',
        'n_componenets',  'n_components',
        'ic_boundary_nodes', 'block_nodes',
    }

    cmap = plt.get_cmap('tab10')
    colors = [cmap(i % 10) for i in range(len(dfs))]

    # Per group: drop the undisrupted baseline row, keep numeric metric columns
    # Remember raw means, then scale for plotting
    processed = []
    raw_means = []
    for df in dfs:
        df = df.drop(index=[idx for idx in df.index if idx == 'default' or idx == ('default', 'default')], errors='ignore')
        numeric_df = df.select_dtypes(include='number').replace({None: np.nan})
        numeric_df = numeric_df.drop(columns=[c for c in numeric_df.columns if c in EXCLUDED_COLS], errors='ignore')
        raw_means.append(numeric_df.mean())

        if scaling == 'zscore':
            scaled = (numeric_df - numeric_df.mean()) / numeric_df.std()
        elif scaling == 'minmax':
            col_min = numeric_df.min(skipna=True)
            col_max = numeric_df.max(skipna=True)
            scaled = (numeric_df - col_min) / (col_max - col_min)
        else:
            scaled = numeric_df.copy()
        scaled = scaled.replace([np.inf, -np.inf], np.nan)  # constant columns divide by zero when scaled
        processed.append(scaled)

    if scaling == 'zscore':
        ylabel = 'Z-score (standardized)'
    elif scaling == 'minmax':
        ylabel = 'Scaled value [0-1]'
    else:
        ylabel = 'Value'

    # Union of metric columns across all groups, in first-seen order
    all_cols = []
    for scaled_df in processed:
        for col in scaled_df.columns:
            if col not in all_cols:
                all_cols.append(col)

    n_groups = len(dfs)
    group_width = 0.8
    box_width = group_width / n_groups

    if metric_groups is None:
        # No grouping requested - everything in a single row, no inset label
        row_chunks = [all_cols]
        row_titles = [None]
    else:
        # One subplot row per metric group. A requested name matches itself and any suffixed
        # variant (name + '_...'), so 'disrupted_pax_flow' also collects the node/block outputs'
        # 'disrupted_pax_flow_sum' without needing separate group definitions per disruption type.
        row_chunks = []
        row_titles = []
        assigned = set()
        for group_name, wanted in metric_groups.items():
            row_cols = []
            for name in wanted:
                for col in all_cols:
                    if col not in assigned and (col == name or col.startswith(name + '_')):
                        row_cols.append(col)
                        assigned.add(col)
            if row_cols:
                row_chunks.append(row_cols)
                row_titles.append(group_name)

        # Used if plotting multiple sub-figure plots into the same figure
        if len(metric_groups) == 1:
            row_titles = [None]
        else:
            # Anything in the data but not named in metric_groups
            leftover = [col for col in all_cols if col not in assigned]

            row_titles = [f"{chr(97 + i)}) {name}" for i, name in enumerate(row_titles)]

    n_rows = len(row_chunks)
    max_row_len = max(len(chunk) for chunk in row_chunks)

    fig, axes = plt.subplots(n_rows, 1, figsize=(figsize[0], max(figsize[1], 4.5 * n_rows)), squeeze=False)
    axes = axes.flatten()

    for row_idx, (ax, row_cols) in enumerate(zip(axes, row_chunks)):
        for g_idx, scaled_df in enumerate(processed):
            for m_idx, col in enumerate(row_cols):
                if col not in scaled_df.columns:
                    continue
                data = scaled_df[col].dropna().values

                # Center each group around the metric tick, offset per group
                x_pos = m_idx + (g_idx - (n_groups - 1) / 2) * box_width

                # Constant column under z-scoring (std=0) or all-NaN: no distribution.
                if data.size == 0:
                    
                    # Plot raw mean anyway
                    raw_mean = raw_means[g_idx].get(col)
                    if raw_mean is not None and not pd.isna(raw_mean):
                        ax.text(
                            x_pos, 0, f' {raw_mean:.3g}',
                            rotation=90, ha='center', va='bottom',
                            fontsize=6, color=colors[g_idx], clip_on=False,
                        )
                    continue

                ax.boxplot(
                    data,
                    positions=[x_pos],
                    widths=box_width * 0.85,
                    patch_artist=True,
                    boxprops=dict(facecolor=colors[g_idx], color=colors[g_idx], alpha=0.6),
                    medianprops=dict(color='black', linewidth=1.5),
                    whiskerprops=dict(color=colors[g_idx]),
                    capprops=dict(color=colors[g_idx]),
                    flierprops=dict(marker='o', markerfacecolor=colors[g_idx], markersize=3, alpha=0.5),
                    showmeans=False,
                    meanprops=dict(marker='D', markerfacecolor='white', markeredgecolor='black', markersize=4),
                    manage_ticks=False
                )

                # Raw (unscaled) mean printed above the box in the group's color
                raw_mean = raw_means[g_idx].get(col)
                if raw_mean is not None and not pd.isna(raw_mean):
                    ax.text(
                        x_pos+0.015, np.nanmax(data)+0.15, f' {raw_mean:.3g}',
                        rotation=90, ha='center', va='bottom',
                        fontsize=6, color=colors[g_idx], clip_on=False,
                    )

        ax.set_xticks(range(len(row_cols)))
        ax.set_xticklabels(row_cols, rotation=45, ha='right', fontsize=9)
        # Fixed to the longest row (not len(row_cols)) so box widths stay visually consistent across rows even when a row holds fewer metrics
        ax.set_xlim(-0.5, max_row_len - 0.5)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        # Headroom for the rotated mean annotations
        ax.margins(y=0.18)

        # Inset label naming this row's metric group (skipped when no metric_groups was given)
        if row_titles[row_idx] is not None:
            ax.text(
                0.005, 0.97, row_titles[row_idx], transform=ax.transAxes,
                ha='left', va='top', fontsize=12, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85, edgecolor='lightgray'),
            )

        if scaling == 'zscore':
            ax.axhline(0, color='gray', linestyle=':', linewidth=0.8)

    # Legend on the first row only: one patch per group, plus the median line and the mean value that appear on/above every box.
    legend_handles = [
        mpatches.Patch(facecolor=colors[i], label=group_labels[i])
        for i in range(n_groups)
    ]
    legend_handles += [
        Line2D([0], [0], color='black', linewidth=1.5, label='Median'),
        Line2D([0], [0], color='gray', marker=r'$\bar{x}$', linestyle='None',
               markersize=9, label='Mean (raw value)'),
    ]
    axes[0].legend(handles=legend_handles, title='Scenario', loc='best', fontsize=8)

    fig.suptitle(title)
    plt.tight_layout()
    fig.savefig(sf.get_dir(f"figures/disruptions/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_measure_boxplots(
    measures: list[dict],
    series_labels: list[str],
    title: str = 'Measure value distributions',
    scaling: str = 'none',   # 'zscore' | 'none'
    figsize: tuple = (7, 4),
    filename: str = 'generic_measure_boxplot',
):
    """
    Boxplots of the value distribution of one or more graph measures.

    Args:
        measures:      list of {key: value} measure dicts, one box each
        series_labels: x-axis label for each measure, same length/order as `measures`
        scaling:       'zscore' or 'none' for raw values
    """
    if len(measures) != len(series_labels):
        raise ValueError(
            f"measures ({len(measures)}) and series_labels ({len(series_labels)}) must be the same length."
        )

    cmap = plt.get_cmap('tab10')
    colors = [cmap(i % 10) for i in range(len(measures))]

    # Collect values and raw mean per series
    plotted   = []
    for measure in measures:
        vals = pd.Series(list(measure.values()), dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
        if scaling == 'zscore':
            std = vals.std()
            # Drop empty series so it's annotated but not boxed.
            scaled = (vals - vals.mean()) / std if std and not np.isnan(std) else pd.Series([], dtype=float)
            plotted.append(scaled)
        else:
            plotted.append(vals)

    ylabel = 'Z-score (standardized)' if scaling == 'zscore' else 'Value'

    fig, ax = plt.subplots(figsize=figsize, dpi=plot_dpi)

    for i, series in enumerate(plotted):
        data = series.values

        ax.boxplot(
            data,
            positions=[i],
            widths=0.6,
            patch_artist=True,
            boxprops=dict(facecolor=colors[i], color=colors[i], alpha=0.6),
            medianprops=dict(color='black', linewidth=1.5),
            whiskerprops=dict(color=colors[i]),
            capprops=dict(color=colors[i]),
            flierprops=dict(marker='o', markerfacecolor=colors[i], markersize=3, alpha=0.5),
            manage_ticks=False,
            meanprops=dict(marker='D', markerfacecolor='white', markeredgecolor='black', markersize=4),
            showmeans=True,
        )

    ax.set_xticks(range(len(series_labels)))
    ax.set_xticklabels(series_labels, rotation=45, ha='right', fontsize=9)
    ax.set_xlim(-0.5, len(series_labels) - 0.5)
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    ax.margins(y=0.18)
    if scaling == 'zscore':
        ax.axhline(0, color='gray', linestyle=':', linewidth=0.8)

    legend_handles = [
        Line2D([0], [0], color='black', linewidth=1.5, label='Median'),
        Line2D([0], [0], marker='D', markerfacecolor='white', markeredgecolor='black', markersize=4, label='Mean'),
    ]
    ax.legend(handles=legend_handles, loc='best', fontsize=8)

    fig.suptitle(title)
    plt.tight_layout()
    fig.savefig(sf.get_dir(f"figures/measures/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_highlighted_graph(
    G: nx.Graph,
    pos: dict,
    highlight_type: str,
    title_str: str = "Graph",
    label_type: str = None,
    node_size: int = 8,
    edge_width: float = 1.0,
    filename:str = 'generic_highlight'
):
    """
    Plots a single graph, highlighting nodes and edges connected to at least
    one node with a specific 'Type' attribute value.

    Args:
        G:              nx.Graph
        pos:            dict of node positions
        highlight_type: value of the 'type' attribute to highlight
        title_str:      string to use as title
        label_type:     "all" = all labels, "ic" = ic stations only, None = none
        node_size:      base node size
        edge_width:     base edge width
    """
    # Partition nodes
    highlight_nodes = [n for n, d in G.nodes(data=True) if d.get("Type") == highlight_type]
    normal_nodes    = [n for n in G.nodes() if n not in highlight_nodes]

    # Highlight if at least one endpoint has the Type
    highlight_node_set = set(highlight_nodes)
    highlight_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if u in highlight_node_set
        or v in highlight_node_set
        or d.get("type") == highlight_type
    ]
    normal_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if (u, v) not in set(highlight_edges)
    ]

    fig, ax = plt.subplots(1, 1, figsize=(7, 8), dpi=plot_dpi)
    ax.set_title(title_str)

    # Draw normal elements
    nx.draw_networkx_nodes(G, pos=pos,
                           nodelist=normal_nodes,
                           node_color="steelblue",
                           edgecolors="k",
                           linewidths=0.5,
                           node_size=node_size,
                           ax=ax)
    nx.draw_networkx_edges(G, pos=pos,
                           edgelist=normal_edges,
                           edge_color="grey",
                           width=edge_width,
                           ax=ax)

    # Draw highlighted elements
    nx.draw_networkx_nodes(G, pos=pos,
                           nodelist=highlight_nodes,
                           node_color="orange",
                           #edgecolors="k",
                           linewidths=0.5,
                           node_size=node_size * 2,
                           ax=ax)
    nx.draw_networkx_edges(G, pos=pos,
                           edgelist=highlight_edges,
                           edge_color="orange",
                           width=edge_width * 1.5,
                           ax=ax)

    # Labels
    nodes_to_label = ic_node_labels(G)
    if label_type == "ic":
        nx.draw_networkx_labels(G, pos=pos, font_size=8, labels=nodes_to_label, ax=ax)
    elif label_type == "all":
        nx.draw_networkx_labels(G, pos=pos, font_size=8, ax=ax)
    elif label_type == "highlight":
        nx.draw_networkx_labels(G, pos=pos, font_size=8,
                                labels={n: n for n in highlight_nodes}, ax=ax)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/interventions/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_centrality_diff(
    G_new: nx.Graph,
    pos: dict,
    centrality_base: dict,
    centrality_new: dict,
    title_str: str = "Centrality Difference",
    label_type: str = None,
    width_scale: float = 5.0,
    no_diff_width: float = 0.3,
    no_diff_size: float = 8.0,
    filename:str='generic_centrality_difference',
    print_output: bool = False,
):
    """
    Plots the difference in a centrality measure between two graphs.
    Works for both node-based and edge-based centrality dicts.

    Args:
        centrality_base:  dict of values
        centrality_new:   dict of values
        width_scale:      max width/size for the largest difference
        no_diff_width:    width/size for unchanged elements
    """
    # Detect whether this is edge or node centrality
    sample_key = next(iter(centrality_base))
    is_edge_centrality = isinstance(sample_key, tuple)

    increased, increased_vals = [], []
    decreased, decreased_vals = [], []
    unchanged = []

    keys = set(centrality_base) | set(centrality_new)
    for key in keys:
        base_val = centrality_base.get(key, 0)
        new_val  = centrality_new.get(key, 0)
        diff = new_val - base_val


        if diff > 0:
            increased.append(key)
            increased_vals.append(diff)
        elif diff < 0:
            decreased.append(key)
            decreased_vals.append(abs(diff))
        else:
            unchanged.append(key)

    centrality_diff_report = {}
    for key in increased:
        centrality_diff_report[key] = round(centrality_new.get(key, 0) - centrality_base.get(key, 0), 5)
    for key in decreased:
        centrality_diff_report[key] = round(centrality_new.get(key, 0) - centrality_base.get(key, 0), 5)

    if print_output:
        for k, v in sorted(centrality_diff_report.items(), key=lambda x: x[1], reverse=True):
            print(f"{k}: {v}")

    # Normalise
    max_diff = max(increased_vals + decreased_vals, default=1)
    increased_vals = [v / max_diff * width_scale for v in increased_vals]
    decreased_vals = [v / max_diff * width_scale for v in decreased_vals]

    fig, ax = plt.subplots(1, 1, figsize=(7, 8), dpi=plot_dpi)

    if is_edge_centrality:
        nx.draw_networkx_nodes(G_new, pos=pos, node_size=8,
                               edgecolors="k", linewidths=0.5, ax=ax)
        nx.draw_networkx_edges(G_new, pos=pos, edgelist=unchanged,
                               edge_color="black", width=no_diff_width, ax=ax)
        if increased:
            nx.draw_networkx_edges(G_new, pos=pos, edgelist=increased,
                                   edge_color="green", width=increased_vals, ax=ax)
        if decreased:
            nx.draw_networkx_edges(G_new, pos=pos, edgelist=decreased,
                                   edge_color="red", width=decreased_vals, ax=ax)
    else:
        # Draw all edges in neutral
        nx.draw_networkx_edges(G_new, pos=pos, edge_color="grey",
                               width=no_diff_width, ax=ax)
        nx.draw_networkx_nodes(G_new, pos=pos, nodelist=unchanged,
                               node_color="black", node_size=no_diff_size,
                               edgecolors="k", linewidths=0.5, ax=ax)
        if increased:
            nx.draw_networkx_nodes(G_new, pos=pos, nodelist=increased,
                                   node_color="green", node_size=increased_vals,
                                   edgecolors="k", linewidths=0.5, ax=ax)
        if decreased:
            nx.draw_networkx_nodes(G_new, pos=pos, nodelist=decreased,
                                   node_color="red", node_size=decreased_vals,
                                   edgecolors="k", linewidths=0.5, ax=ax)

    # Labels
    if label_type == "ic":
        nx.draw_networkx_labels(G_new, pos=pos, font_size=8,
                                labels=ic_node_labels(G_new), ax=ax)
    elif label_type == "all":
        nx.draw_networkx_labels(G_new, pos=pos, font_size=8, ax=ax)

    # Legend
    legend_elements = [
        Line2D([0], [0], color="green", linewidth=2, label="Increased"),
        Line2D([0], [0], color="red",   linewidth=2, label="Decreased"),
        Line2D([0], [0], color="black", linewidth=1, label="No change"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    fig.tight_layout()
    fig.suptitle(title_str)
    fig.savefig(sf.get_dir(f"figures/interventions/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_blocks(G_tracks: nx.Graph, pos: dict,strictness:int,n_blocks:int):
    """
    Greedy graph coloring of the track blocks.
    """
    # Build block adjacency (conflict graph)-
    # Two blocks conflict if they share an IC endpoint node
    block_endpoints = {}  # block_id -> set of endpoint nodes
    for u, v, data in G_tracks.edges(data=True):
        bid = data.get('block_id')
        if bid is None:
            continue
        block_endpoints.setdefault(bid, set())
        for node in (u, v):
            if G_tracks.nodes[node].get('ic_station'):
                block_endpoints[bid].add(node)

    conflict_graph = nx.Graph()
    conflict_graph.add_nodes_from(block_endpoints.keys())
    endpoint_to_blocks = {}
    for bid, endpoints in block_endpoints.items():
        for ep in endpoints:
            endpoint_to_blocks.setdefault(ep, []).append(bid)
    for blocks in endpoint_to_blocks.values():
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                conflict_graph.add_edge(blocks[i], blocks[j])

    # Greedy graph coloring
    coloring = nx.coloring.greedy_color(conflict_graph, strategy='largest_first')
    num_colors = max(coloring.values()) + 1
    cmap = plt.cm.get_cmap('tab10', num_colors)
    block_color = {bid: cmap(coloring[bid]) for bid in coloring}

    # Plot
    fig, ax = plt.subplots(figsize=(12, 8))

    # Untagged edges (passed edges due to yards, borders) in gray
    untagged_edges = [(u, v) for u, v, d in G_tracks.edges(data=True) if 'block_id' not in d]
    nx.draw_networkx_edges(G_tracks, pos, edgelist=untagged_edges, edge_color='lightgray', ax=ax)

    # Tagged edges per block
    for bid, color in block_color.items():
        edges = [(u, v) for u, v, d in G_tracks.edges(data=True) if d.get('block_id') == bid]
        nx.draw_networkx_edges(G_tracks, pos, edgelist=edges, edge_color=[color], width=2, ax=ax)

    # Untagged nodes (IC stations) in black
    untagged_nodes = [n for n, d in G_tracks.nodes(data=True) if ('block_id' not in d) and d.get('ic_station')]
    nx.draw_networkx_nodes(G_tracks, pos, nodelist=untagged_nodes, node_color='black', node_size=70, ax=ax)

    # Tagged nodes per block
    for bid, color in block_color.items():
        nodes = [n for n, d in G_tracks.nodes(data=True) if d.get('block_id') == bid]
        nx.draw_networkx_nodes(G_tracks, pos, nodelist=nodes, node_color=[color], node_size=20, ax=ax)

    legend_elements = [
        Line2D([0], [0], marker='o', color='none', label='Block terminus',
               markerfacecolor='black', markeredgecolor='black', markersize=7),
    ]
    ax.legend(handles=legend_elements, loc='lower right')

    title = f"Track blocks with strictness = {strictness}, number of blocks = {n_blocks}"
    ax.set_title(title)
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.tight_layout()
    fig.savefig(sf.get_dir(f"figures/block_graph_with_{strictness}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_basic_graph(
    infra: nx.Graph,
    pos_segments: dict,
    title_str: str = "Track Graph",
    services: nx.Graph = None,
    pos_nodes: dict = None,
    label_type: str = None,
    stack: str = "horizontal",
    filename: str = 'generic_basic_graph'
):
    """
    Generic plotting function for infrastructure and (optionally) service graphs.
    If only `infra` is provided, renders a single full-size figure.
    If `services` is also provided, renders a figure with two side-by-side (or stacked) subplots.

    Args:
        infra:          nx.Graph — infrastructure/track graph (always plotted)
        pos_segments:   dict of infra node positions
        pos_nodes:      dict of service node positions
        title_str:      string to use as the figure title
        services:       nx.Graph — optional service graph; triggers dual-subplot layout if passed
        label_type:     "all" = all labels, "ic" = IC stations only, "infra" = connection nodes only
        stack:          "horizontal" (side by side) or "vertical" (stacked)
    """
    nodes_to_label = ic_node_labels(infra)

    def _setup_ax(ax):
        ax.set_xlim(3.5, 7.3)
        ax.set_ylim(50.6, 53.5)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)

    def _draw_graph(G, pos, ax, label_type, nodes_to_label):
        nx.draw_networkx_nodes(G, pos=pos, edgecolors='k', linewidths=0.5, node_size=8, ax=ax)
        nx.draw_networkx_edges(G, pos=pos, width=edge_width, ax=ax)
        if label_type == "ic":
            nx.draw_networkx_labels(G, pos=pos, font_size=8, labels=nodes_to_label, ax=ax)
        elif label_type == "all":
            nx.draw_networkx_labels(G, pos=pos, font_size=8, ax=ax)
        elif label_type == "infra":
            nx.draw_networkx_labels(
                G, pos=pos, font_size=8,
                labels={n: n for n, d in G.nodes(data=True) if d.get("Type") == "connection"},
                ax=ax,
            )

    # Single graph
    if services is None:
        fig, ax = plt.subplots(1, 1, figsize=(5, 7), dpi=plot_dpi)
        ax.set_title(title_str)
        _draw_graph(infra, pos_segments, ax, label_type, nodes_to_label)
        _setup_ax(ax)
        fig.tight_layout()

    # Dual graph
    else:
        nodes_to_label_services = ic_node_labels(services)
        nrows, ncols = (2, 1) if stack == "vertical" else (1, 2)
        fig, (ax1, ax2) = plt.subplots(nrows, ncols, figsize=(7, 4), sharex=True, sharey=True, dpi=plot_dpi)

        ax1.set_title("Track graph")
        _draw_graph(infra, pos_segments, ax1, label_type, nodes_to_label)

        ax2.set_title("Service graph")
        # Pass service-specific labels for ic/all modes
        service_labels = nodes_to_label_services if label_type == "ic" else nodes_to_label
        _draw_graph(services, pos_nodes, ax2, label_type, service_labels)

        for ax in (ax1, ax2):
            _setup_ax(ax)

        fig.suptitle(title_str)
        fig.tight_layout()

    fig.savefig(sf.get_dir(f"figures/basic/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_infrastructure_comparison(infra: nx.Graph, ic_graph: nx.Graph, pos_segments: dict, label_type: str = None, plot_tracks: bool = True, filename: str = 'basic_graph_comparison',title:str="Edge comparison between train and bus graphs"):
    """
    Plots the OV segments over the track graph.

    Edge colors:
        - Black:  edge exists only in lfet graph
        - Green:  edge exists in both left and right graph
        - Red:    edge exists only in right
    """
    ic_nodes = ic_node_labels(infra)
    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    ax.set_title(title)

    if plot_tracks:
        # Build edge sets for comparison
        infra_edges = {frozenset([u, v]) for u, v, *_ in infra.edges()}
        ov_edges    = {frozenset([u, v]) for u, v, *_ in ic_graph.edges()}

        only_tracks  = [(u, v) for u, v in infra.edges() if frozenset([u, v]) not in ov_edges]
        shared_edges = [(u, v) for u, v in infra.edges() if frozenset([u, v]) in ov_edges]
        only_ov      = [(u, v) for u, v in ic_graph.edges() if frozenset([u, v]) not in infra_edges]

        nodes_tracks = nx.draw_networkx_nodes(
            infra,
            pos=pos_segments,
            edgecolors='k',
            linewidths=0.5,
            node_size=4,
            ax=ax)
        nodes_tracks.set_zorder(4)

        # Black: only in G_tracks
        if only_tracks:
            e = nx.draw_networkx_edges(
                infra, pos=pos_segments,
                edgelist=only_tracks,
                edge_color='black',
                width=edge_width,
                alpha=0.6,
                ax=ax)
            e.set_zorder(3)

        # Green: in both graphs
        if shared_edges:
            e = nx.draw_networkx_edges(
                infra, pos=pos_segments,
                edgelist=shared_edges,
                edge_color='green',
                width=edge_width + 1,
                alpha=0.9,
                ax=ax)
            e.set_zorder(2)

        # Red: only in G_ov
        if only_ov:
            e = nx.draw_networkx_edges(
                ic_graph, pos=pos_segments,
                edgelist=only_ov,
                edge_color='red',
                width=edge_width + 1,
                alpha=0.9,
                ax=ax)
            e.set_zorder(1)

        legend_elements = [
            mpl.lines.Line2D([0], [0], color='black', label='Train only'),
            mpl.lines.Line2D([0], [0], color='green', lw=2, label='Train + line bus'),
            mpl.lines.Line2D([0], [0], color='red',   lw=2, label='Line bus only'),
        ]

    # IC nodes on top
    nodes_ic = nx.draw_networkx_nodes(
        ic_graph,
        pos=pos_segments,
        nodelist=ic_nodes,
        node_color='r',
        edgecolors='k',
        linewidths=0.5,
        node_size=8,
        ax=ax)
    nodes_ic.set_zorder(4)

    if label_type == "ic":
        nx.draw_networkx_labels(infra, pos=pos_segments, font_size=8, labels=ic_nodes, ax=ax)

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(handles=legend_elements, loc='best')
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)
    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_graph_edge_attr_greedy(
    G: nx.Graph,
    pos: dict,
    attr: str,
    title: str = None,
    filename: str = 'graph_edge_attr',
    node_size: int = 5,
    base_edge_width: float = None,
    alpha: float = 0.8,
    cmap_name: str = 'tab10',
):
    """
    Plots a graph with edges greedy-colored by a given edge attribute.
    Edges sharing the same attribute value receive the same color, assigned
    so that no two adjacent (node-sharing) edges with the same color conflict.

    Args:
        G            : NetworkX graph to plot
        pos          : position dict
        attr         : edge attribute name to color by
        title        : plot title 
        filename     : output filename
        node_size    : node marker size
        base_edge_width : edge line width 
        alpha        : edge alpha
        cmap_name    : colormap
    """
    _edge_width = base_edge_width if base_edge_width is not None else edge_width

    #  Build a line graph for greedy coloring
    # Each edge in G becomes a node in L, two L-nodes are adjacent if the original edges share a vertex.
    L = nx.line_graph(G)
    coloring = nx.coloring.greedy_color(L, strategy='largest_first')

    # Group edges by (attribute value, color_int) 
    # Two edges with the same attr value may still get different ints if they are adjacent
    attr_to_color_int: dict = {} 
    edge_groups: dict = {}

    for edge_key, color_int in coloring.items():
        u, v = edge_key[0], edge_key[1]
        attr_val = G[u][v].get(attr) if not G.is_multigraph() else (
            G[u][v][edge_key[2]].get(attr) if len(edge_key) > 2 else None
        )

        # Map each attr value to a stable color int
        if attr_val not in attr_to_color_int:
            attr_to_color_int[attr_val] = color_int
        stable_int = attr_to_color_int[attr_val]

        edge_groups.setdefault(stable_int, []).append((u, v))

    # Assign colors from colormap
    n_colors = max(edge_groups.keys()) + 1 if edge_groups else 1
    cmap = plt.get_cmap(cmap_name, max(n_colors, 1))
    color_map = {ci: cmap(ci) for ci in edge_groups}

    # Plot
    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)
    ax.set_title(title or f"Edge coloring by '{attr}'")

    nx.draw_networkx_nodes(
        G, pos=pos,
        edgecolors='k',
        linewidths=0.5,
        node_size=node_size,
        ax=ax,
    )

    for color_int, edgelist in edge_groups.items():
        # Only draw edges that still exist in G
        valid = [(u, v) for u, v in edgelist if G.has_edge(u, v)]
        if not valid:
            continue
        nx.draw_networkx_edges(
            G, pos=pos,
            edgelist=valid,
            edge_color=[color_map[color_int]],
            width=_edge_width,
            alpha=alpha,
            ax=ax,
        )

    ax.set_xlim(3.5, 7.3)
    ax.set_ylim(50.6, 53.5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.tick_params(bottom=True, left=True, labelbottom=True, labelleft=True)
    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)

def plot_column_distribution(
    df: pd.DataFrame,
    column: str,
    title: str='generic histogram',
    filename: str='generic_histogram',
    bins: int = 16,
    color: str = "steelblue",
) -> plt.Figure:
    """
    Plot the distribution of a single numeric or categorical DataFrame column.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame.")

    series = df[column].dropna()
    fig, ax = plt.subplots(figsize=(7, 4), dpi=plot_dpi)

    if pd.api.types.is_numeric_dtype(series):
        # Histogram
        counts, edges, patches = ax.hist(
            series, bins=bins, color=color, edgecolor="white", linewidth=0.4, alpha=0.85
        )
        ax.set_xlabel(column, fontsize=10)
        ax.set_ylabel("Count", fontsize=10)

    else:
        # Bar chart of value counts
        vc = series.value_counts().head(20)
        ax.bar(range(len(vc)), vc.values, color=color, edgecolor="white", linewidth=0.4)
        ax.set_xticks(range(len(vc)))
        ax.set_xticklabels(vc.index, rotation=45, ha="right", fontsize=8)
        ax.set_xlabel(f"{column} [%]", fontsize=10)
        ax.set_ylabel("Count", fontsize=10)

    ax.set_title(title, fontsize=11, pad=8)
    ax.tick_params(axis="both", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/demand/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi-50)
    _show(fig)

    return 

def plot_catchment_vs_travelers(stations_df, catchments, filename="scatter_catchment_travelers"):
    """
    Scatter plot of station_catchment (population) vs station demand,
    with a fitted linear regression line, equation, and R² annotation.

    Args:
    stations_df : DataFrame with 'Name' and 'TravelersPerDay'
    catchments  : DataFrame with 'name_long' and 'station_catchment'
    """
    # Merge
    df = stations_df.merge(
        catchments[["name_long", "station_catchment"]],
        how="left",
        left_on="Name",
        right_on="name_long"
    ).dropna(subset=["station_catchment", "demand"])

    x = df["station_catchment"].values
    y = df["demand"].values

    # Power law fit
    valid = (x > 0) & (y > 0)  # log undefined for x or y <= 0
    x_fit, y_fit = x[valid], y[valid]

    log_x = np.log(x_fit)
    log_y = np.log(y_fit)
    b, log_a = np.polyfit(log_x, log_y, 1)
    a = np.exp(log_a)
    r_value, _ = pearsonr(log_x, log_y)  # R2 in log-log space
    r2 = r_value ** 2

    x_line = np.linspace(x.min(), x.max(), 300)
    y_line = a * x_line ** b

    fig, ax = plt.subplots(figsize=(5, 3), dpi=plot_dpi)

    ax.scatter(
        x, y,
        s=40,
        color="steelblue",
        edgecolors="white",
        linewidths=0.4,
        alpha=0.8,
        zorder=3,
    )

    ax.plot(x_line, y_line, color="darkred", linewidth=1.4, zorder=4, label="Linear fit")

    # Equation
    eq_text = (
        f"$y = {a:,.3f} \\cdot x^{{{b:.3f}}}$\n"
        f"$R^2 = {r2:.3f}$"
    )
    ax.annotate(
        eq_text,
        xy=(0.05, 0.88),
        xycoords="axes fraction",
        fontsize=8.5,
        color="darkred",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="darkred", alpha=0.7),
    )

    # Label top 5 outliers
    top = df.nlargest(5, "demand")
    for _, row in top.iterrows():
        ax.annotate(
            row["name_long"],
            xy=(row["station_catchment"], row["demand"]),
            xytext=(5, 3),
            textcoords="offset points",
            fontsize=7,
            color="dimgray",
        )

    ax.set_xlabel("Station population catchment ", fontsize=10)
    ax.set_ylabel("Passenger demand per day", fontsize=10)
    ax.set_title("Station Catchment vs. Station Demand", fontsize=11, pad=8)
    ax.tick_params(axis="both", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5, zorder=0)

    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/demand/{filename}.jpg"), bbox_inches="tight", dpi=plot_dpi)
    _show(fig)
    return

def plot_degree_histogram(G:nx.Graph, title:str='Degree histogram'):
    degree_sequence = [d for n, d in G.degree() if d > 0]
    fit = powerlaw.Fit(degree_sequence, verbose=0,discrete=True)

    fig, ax = plt.subplots(figsize=(5, 3), dpi=200)

    # Histogram bars
    counts = Counter(degree_sequence)
    total = len(degree_sequence)
    degrees = sorted(counts)
    probs = [counts[d] / total for d in degrees]
    ax.bar(degrees, probs, color='steelblue', alpha=0.6, label='Empirical')

    # Powerlaw overlays
    fit.power_law.plot_pdf(color='g', linestyle='--', ax=ax, label=f'Power law (α={fit.alpha:.2f})')

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_title(title)
    ax.set_ylabel("Degree frequency")
    ax.set_xlabel("Degree")
    ax.legend()
    fig.tight_layout()
    fig.savefig(sf.get_dir(f"figures/basic/{title}.jpg"), bbox_inches="tight", dpi=plot_dpi-50)
    _show(fig)
    return
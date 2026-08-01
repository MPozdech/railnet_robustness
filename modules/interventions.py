import modules.data_preparation     as dp          # type: ignore
import modules.demand               as demand      # type: ignore
import modules.disruptions          as disruptions # type: ignore
import modules.metrics              as metrics     # type: ignore
import modules.plotting             as plotting    # type: ignore
import modules.supporting_functions as sf          # type: ignore
import pandas as pd
import networkx as nx
import numpy as np

"""
Handles everything from creating the new stations, running the scenarios, calculating differences. 

Only does it for the track graph and edge betweenness measure.  
"""

#### Shared inputs
G_tracks = None
G_services = None
G_ipv = None
G_ov = None
pos_tracks = {}
baseline_no_alternative = None
baseline_ipv_alt = None
baseline_ov_alt = None
old_track_betweenness = {}

# Takes new stations and returns graph based on import choice.
new_stations = dp.pg_import("catchments_new_stations") # The name of new stations, their catchments, and lat-longs
new_stations['TravelersPerDay'] = round(0.264 * new_stations['pax_catchment'] ** 0.9607,0) # Should have this passed from the fitting in dp
pos_new = dict(
    zip(
        new_stations['station_name'],
        zip(new_stations['longitude'],new_stations['latitude'])
    )
)
new_stations['Type'] = 'new'
new_stations.set_index('station_name',inplace=True)

def add_new_stations(G:nx.Graph,trajects:list[str]=['nedersaksenlijn']):
    """
    Take the input graph and add the trajects listed out.
    trajects=['afsluitdijk','lelylijn','lelylijn_extension','nedersaksenlijn']
    """

    known_edges = pd.DataFrame({
        'geo_length': nx.get_edge_attributes(G,'geo_length'),
        'speed':      nx.get_edge_attributes(G,'speed'),
    })

    # Get the median value for % of 24hr demand
    median_morningrush = np.median(list(nx.get_node_attributes(G,'MorningRush').values()))
    new_stations['MorningRush'] = median_morningrush
    new_stations['MorningDemand'] = round((median_morningrush / 100) * new_stations['TravelersPerDay'],0)

    G_new = G.copy()
    def _tt_func(distance:float, known_edges:pd.DataFrame) -> float:
        # Use the speed of the known edge whose geo_length is closest to the new edge's length
        nearest_idx = (known_edges['geo_length'] - distance).abs().idxmin()
        speed = known_edges.loc[nearest_idx, 'speed']
        edge_travel_time = round((distance / speed),1)
        return edge_travel_time

    # Add Afsluitdijk traject
    if any(elem in ['afsluitdijk'] for elem in trajects):
        distance = 78.35 #km
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Dronryp','Heerhugowaard',geo_length=distance,travel_time=edge_travel_time,type='new')

    # Add Lelylijn traject
    if any(elem in ['lelylijn'] for elem in trajects):

        # Add new stations
        station_names = ["Emmeloord"]
        for station_name in station_names:
            row = new_stations.loc[station_name]  
            G_new.add_node(station_name, **row[['Type','TravelersPerDay','MorningRush','MorningDemand']].to_dict())

        # Add new edges
        distance = 30.25
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Emmeloord','Lelystad Centrum',geo_length=distance,travel_time=edge_travel_time,type='new')

        distance = 29.41
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Emmeloord','Heerenveen',geo_length=distance,travel_time=edge_travel_time,type='new')


    # Add Nedersaksenlijn traject
    if any(elem in ['nedersaksenlijn'] for elem in trajects):

        # Add new stations
        station_names = ["Stadskanaal", "Ter Apel"]
        for station_name in station_names:
            row = new_stations.loc[station_name]
            G_new.add_node(station_name, **row[['Type','TravelersPerDay','MorningRush','MorningDemand']].to_dict())

        # Add new edges
        distance = 12.56
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Stadskanaal','Veendam',geo_length=distance,travel_time=edge_travel_time,type='new')

        distance = 15.12
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Stadskanaal','Ter Apel',geo_length=distance,travel_time=edge_travel_time,type='new')

        distance = 13.94
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Emmen','Ter Apel',geo_length=distance,travel_time=edge_travel_time,type='new')

    # Add extension to Groningen
    if any(elem in ['lelylijn_extension'] for elem in trajects):

        # Add new stations
        station_names = ["Drachten", "Leek"]
        for station_name in station_names:
            row = new_stations.loc[station_name]
            G_new.add_node(station_name, **row[['Type','TravelersPerDay','MorningRush','MorningDemand']].to_dict())

        distance = 19.44
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Drachten','Heerenveen',geo_length=distance,travel_time=edge_travel_time,type='new')

        distance = 19.61
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Drachten','Leek',geo_length=distance,travel_time=edge_travel_time,type='new')

        distance = 13.96 
        edge_travel_time = _tt_func(distance,known_edges)
        G_new.add_edge('Groningen','Leek',geo_length=distance,travel_time=edge_travel_time,type='new')

    return G_new, pos_new

def show_experiments(title: str = "Intervention trajects", label_type: str = None, filename: str = 'intervention_trajects'):
    """
    Used to plot the different intervention scenarios.
    """
    # Add all interventions to a graph (could be cleaned to subsequent interventions don't have to re-add every time?)
    all_trajects = ['afsluitdijk', 'lelylijn', 'lelylijn_extension', 'nedersaksenlijn']
    G_all, pos_new = add_new_stations(G_tracks, trajects=all_trajects)
    pos_all = {**pos_tracks, **pos_new}

    plotting.plot_intervention_trajects(
        G_all, pos_all, new_stations=new_stations,
        title_str=title, label_type=label_type, filename=filename,
    )

    return

def compare_targeted_edge_disruptions(default_metrics:pd.DataFrame, intervention_metrics:dict, target1:str, target2:str):
    """
    Takes the default metrics and compares the values for the intervention metrics for some targeted edge.
    """

    # Extract the relevant row for this target
    try:
        metric_row = default_metrics.loc[(target1,target2)]
    except KeyError:
        metric_row = default_metrics.loc[(target2,target1)]

    delta_row = {}
    output = {}
    for key in metric_row.keys():
        if key in ['source','target','graph_connected','disconnected_nodes','total_alt_capacity','delta_alt_capacity']:
            delta_row[key] = None
            output[key] = [intervention_metrics[key],metric_row[key],delta_row[key]]
            continue


        # Guard against subtracting NaNs
        intervention_val = intervention_metrics[key]
        default_val = metric_row[key]
        if intervention_val is None or default_val is None or pd.isna(intervention_val) or pd.isna(default_val):
            delta_metric = None
        else:
            delta_metric = intervention_val - default_val

        delta_row[key] = delta_metric

        output[key] = [intervention_metrics[key],metric_row[key],delta_row[key]]

    dicts = [intervention_metrics,metric_row,delta_row]

    df = pd.DataFrame(dicts)   # each dict = one row
    result = df.T
    result.rename(columns={0: 'improved scenario', 1 : 'default scenario', 2 : 'difference'}, inplace=True)

    return result

def combine_scenario_metrics(default: dict,no_alternative: dict,ipv_alt: dict,ov_alt: dict,column_labels: tuple = ('default', 'no alternative', 'ov','ipv')) -> pd.DataFrame:
    """
    Combine a targeted disruption's replacement-scenario metric dicts into one dataframe.
    Metrics as rows, one column per scenario.

    All four inputs are {metric: value} dicts. 
    """
    scenarios = [default, no_alternative, ov_alt,ipv_alt]

    # Default metrics first, then extras
    ordered_keys = []
    for scenario in scenarios:
        for key in scenario:
            if key not in ordered_keys:
                ordered_keys.append(key)

    combined = pd.DataFrame(
        {label: pd.Series(scenario) for label, scenario in zip(column_labels, scenarios)}
    ).reindex(ordered_keys)

    return combined

def combine_scenario_comparisons(
    default_cmp: pd.DataFrame,
    no_alternative_cmp: pd.DataFrame,
    ov_cmp: pd.DataFrame,
    ipv_cmp: pd.DataFrame,
    scenario_labels: tuple = ('default', 'no_alt', 'ov', 'ipv'),
) -> pd.DataFrame:
    """
    Stack the per-scenario comparison frames side by side into one wide dataframe (metrics as rows).
    """
    comparisons = [default_cmp, no_alternative_cmp, ov_cmp, ipv_cmp]
    rename = {'improved scenario': 'improved', 'default scenario': 'default', 'difference': 'difference'}

    pieces = []
    for label, cmp in zip(scenario_labels, comparisons):
        piece = cmp.rename(columns=rename)
        piece.columns = [f"{col}_{label}" for col in piece.columns]
        pieces.append(piece)

    # Row order: union of metrics across all scenarios
    ordered_index = []
    for cmp in comparisons:
        for idx in cmp.index:
            if idx not in ordered_index:
                ordered_index.append(idx)

    combined = pd.concat(pieces, axis=1).reindex(ordered_index)
    return combined

def compare_interventions(scenario_metrics: dict, scenario: str = 'default') -> pd.DataFrame:
    """
    Compare one replacement scenario across several interventions.

    Takes the combined metric tables returned by run_intervention_scenario 
    and pulls out one col from each.

    Args:
        scenario_metrics: {intervention label: metrics dataframe}. Column order follows the dict's insertion order.
        scenario: which column to pull from each table - 'default','no alternative', 'ov' or 'ipv' for the metric tables..

    Returns:
        DataFrame with metrics as rows and one column per intervention.
    """
    if not scenario_metrics:
        raise ValueError("scenario_metrics is empty - pass at least one {label: dataframe} entry.")

    missing = {label: list(df.columns) for label, df in scenario_metrics.items() if scenario not in df.columns}
    if missing:
        label, available = next(iter(missing.items()))
        raise KeyError(
            f"scenario '{scenario}' not found in the metrics for '{label}'. Available columns: {available}"
        )

    # Row order: union of metrics across every intervention, first-seen order
    ordered_index = []
    for df in scenario_metrics.values():
        for idx in df.index:
            if idx not in ordered_index:
                ordered_index.append(idx)

    combined = pd.DataFrame(
        {label: df[scenario] for label, df in scenario_metrics.items()}
    ).reindex(ordered_index)

    return combined

def run_intervention_scenario(
    trajects: list[str],
    target1: str,
    target2: str,
    morning_demand: bool = True,
    scenario_name: str = 'intervention',
) -> tuple:
    """
    Runs one intervention scenario.

    Adds the new line(s)
    Travel time set by using the speed from an existing edge which has the closest distance to the new line.
    Assigns demand again with new lines.
    Calculates edge betweenness on this     
    Disrupts the targeted edge.
    Recalculates demand in the disrupted scenario
    Returns metrics for scenario. 
    """
    # Implement intervention
    G_new, pos_new = add_new_stations(G_tracks, trajects=trajects)
    pos_all = {**pos_tracks, **pos_new}

    plotting.plot_highlighted_graph(
        G_new, pos_all, highlight_type='new',
        title_str=f'New elements being added - {scenario_name}', label_type='highlight',
        filename=f'new_elements_{scenario_name}',
    )

    G_new_demand = demand.assign_flows(
        G_new,morning_demand=morning_demand, apply_override=False,
    )
    nodes_new, edges_new = sf.graph_to_dataframes(G_new_demand)

    plotting.plot_flow_diff(
        G_tracks, G_new_demand, pos_all,
        title_str=f'Flow difference - {scenario_name}',
        filename=f'flow_diff_{scenario_name}',
    )

    plotting.plot_rdt_edge_metric(G_new_demand, pos_all, edge_attribute='flow', title=f'Passenger flow - {scenario_name}', filename=f'flow_{scenario_name}', colorbar_label='Morning rush hour passengers')

    #
    new_track_betweenness = nx.edge_betweenness_centrality(G_new_demand, normalized=True, weight='travel_time')
    plotting.plot_edge_measure(
        G_tracks, G_new_demand, pos_all, pos_all,
        old_track_betweenness, new_track_betweenness,
        title_str=f'Old vs new betweenness - {scenario_name}',
        filename=f'betweenness_old_vs_new_{scenario_name}',
        save_dir='interventions',
    )
    plotting.plot_centrality_diff(
        G_new_demand, pos_all, old_track_betweenness, new_track_betweenness,
        title_str=f'Betweenness comparison - {scenario_name}',
        filename=f'betweenness_diff_{scenario_name}'
    )

    # Re-run the targeted disruption on the improved graph, then compare each scenario against the default metrics for this disruption
    targeted_no_alternative, targeted_ipv_alt, targeted_ov_alt = disruptions.targeted_edge_disruption(
        G_new_demand, G_services, G_ipv, G_ov, target1=target1, target2=target2, morning_demand=morning_demand)

    difference_no_alternative = compare_targeted_edge_disruptions(baseline_no_alternative, targeted_no_alternative, target1=target1, target2=target2)
    difference_ipv_alt        = compare_targeted_edge_disruptions(baseline_ipv_alt, targeted_ipv_alt, target1=target1, target2=target2)
    difference_ov_alt         = compare_targeted_edge_disruptions(baseline_ov_alt, targeted_ov_alt, target1=target1, target2=target2)

    # Undisrupted baseline for the improved network
    default_metrics = metrics.edge_metrics(G_new_demand, source=None, target=None)

    # One-table metric summary: metrics as rows, a column each for default/no-alt/ov/ipv 
    combined_metrics = combine_scenario_metrics(default_metrics, targeted_no_alternative, targeted_ipv_alt, targeted_ov_alt)

    # Undisrupted comparison
    difference_default = compare_targeted_edge_disruptions(baseline_no_alternative, default_metrics, target1='default', target2='default')

    # Disrupted comparison
    combined_comparison = combine_scenario_comparisons(
        difference_default, difference_no_alternative, difference_ov_alt, difference_ipv_alt,
    )

    print(f"Finished intervention analysis of {scenario_name}")

    return (
        G_new_demand, pos_all,
        nodes_new, edges_new, new_track_betweenness,
        combined_metrics, combined_comparison,
    )
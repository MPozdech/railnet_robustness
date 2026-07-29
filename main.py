import modules.data_preparation     as dp       # type: ignore
import modules.supporting_functions as sf       # type: ignore
import modules.measures      as measures        # type: ignore
import modules.demand        as demand          # type: ignore
import modules.plotting      as plotting        # type: ignore
import modules.disruptions   as disruptions     # type: ignore
import modules.interventions as interventions   # type: ignore
import modules.metrics       as metrics         # type: ignore
import networkx as nx                           # type: ignore
import time

############ Script parameters ############
#### Plotting parameters ####
# Do I want the plots to pop up in the viewer? (figures are always created and saved either way)
plotting.show_plots = False
# What dpi do I want for the figures?
plotting.plot_dpi = 200

#### Demand assignment parameters ####
# Do I want to calculate the gravity function parameters from scratch?
ASSIGN_DEMAND   = False
# Do I want infra_model & services_model to have flows for morning peak or for the 24hr period? 
MORNING_DEMAND  = True
# What is the (initial) decay parameter for the gravity function? 
DECAY           = 1.8888
# What is the (initial) scale factor for the gravity function?
SCALE_FACTOR    = 1.343732

#### Disruption experiments ####
# Do I want to run the disruption experiments?
RUN_BLOCK_EXP   = False
RUN_EDGE_EXP    = False 
RUN_NODE_EXP    = False

#### Other ####
# Do I want to export the metric and correlation results to csv?
EXPORT = False
# How many matching nodes between two block segments do I want to create a block?
NUM_MATCHING_NODES_REQUIRED = 1


#### Bus alternatives ####
# How many passengers can fit into an ipv bus?
CAPACITY_IPV_BUS = 50   #pax/vehicle
# How many passengers can fit into an ov bus?
CAPACITY_OV_BUS  = 90   #pax/vehicle
# What is the assumed headway for a bus if none found in GTFS?
DEFAULT_HEADWAY  = 30   #minutes/vehicle

# What are the stations I want to check with a targeted disruption?
TARGET1 = 'Zwolle'
TARGET2 = 'Meppel'

start_time = time.time()
print(f"Script started at: {time.strftime('%H:%M:%S')}")


############ Graph construction ############
# Load psql tables
services             = dp.pg_import("d25_pairs")                        # GTFS service data         - DIRECTED EDGELIST
stations             = dp.pg_import("stations")                         # RDT station data          - NODELIST w/ IC bool
services_disrupted   = dp.pg_import("disrupted_services_combined")      # RDT service cancellations - DIRECTED EDGELIST
services_ipv         = dp.pg_import("ipv_services")                     # RDT IPV services (raw)    - DIRECTED EDGELIST
disruption_durations = dp.pg_import("disruptions_combined")             # RDT disruption data (raw) - 1 ROW = 1 DISRUPTION
replacement_coverage = dp.pg_import("disruption_replacement_services")  # RDT IPV availability      - 1 ROW = 1 DISRUPTION
ov_24                = dp.pg_import("ov_24")                            # OV Oost demand data       - NODELIST w/ pax-per-day
catchments           = dp.pg_import("catchments")                       # Population in catchments  - NODELIST w/ pop-per-station
services_ov          = dp.pg_import("ov_station_edgelist")              # Direct ov connections     - DIRECTED EDGELIST

# Load the JSON data
track_nodes, tracks  = dp.json_import("data/2024_demand_data.json")     # NS track, node, and flows - UNDIRECTED EDGELIST + NODELIST 

# Assign undirected pk index to directed edgelists
services           = dp.make_edge_key(services,           src='from_stop',          dst='to_stop')
services_ipv       = dp.make_edge_key(services_ipv,       src='departure_station',  dst='arrival_station')
services_disrupted = dp.make_edge_key(services_disrupted, src='departure_station',  dst='arrival_station')
services_ov        = dp.make_edge_key(services_ov,        src='source_station_name',dst='target_station_name') 

# Join all the separate tables into those three used to construct the graphs
tracks      = dp.segment_joining(tracks, track_nodes, services, services_ipv, services_ov,CAPACITY_IPV_BUS,CAPACITY_OV_BUS,DEFAULT_HEADWAY) 
track_nodes = dp.stations_joining(track_nodes, stations, ov_24, catchments,export=EXPORT)
services    = dp.node_pairs_joining(services,track_nodes,services_disrupted,disruption_durations,services_ipv,services_ov,CAPACITY_IPV_BUS,CAPACITY_OV_BUS,DEFAULT_HEADWAY)

# Plot data
plotting.plot_column_distribution(track_nodes,'MorningRush',title=f'Morning Demand % Histogram',filename='MorningPeak_histogram',bins=16)
plotting.plot_catchment_vs_travelers(track_nodes,catchments,filename='scatter_catchment_travelers')
disruption_bins = [0,60,2*60,3*60,4*60,5*60,6*60,7*60,8*60,9*60,10*60,11*60,12*60,13*60,14*60,15*60,16*60,17*60,18*60,19*60,20*60,21*60,22*60,23*60,24*60]
plotting.plot_ipv_coverage_by_duration(replacement_coverage,bins=disruption_bins,filename='ipv_coverage_by_duration',title='The percentage of disruptions that had an IPV service provided')

# Extract the positions of the nodes and segments that are passed for plotting later
pos_stations = dp.coord_positions(stations, "stations")
pos_tracks   = dp.coord_positions(tracks,   "segments_df")

# Create the graphs
G_tracks   = nx.from_pandas_edgelist(tracks,   "Name_from", "Name_to", True)
G_services = nx.from_pandas_edgelist(services, "from_stop", "to_stop", True)    

# Attach track elements to service edges
G_services = dp.attach_track_nodes_to_service_edges(G_services,G_tracks)

# Set node attributes from stations_df
G_tracks   = sf.set_node_attributes_from_dataframe(G_tracks,   track_nodes)
G_services = sf.set_node_attributes_from_dataframe(G_services, track_nodes)
plotting.plot_basic_graph(G_tracks,pos_tracks,"Service and Track Graphs - planned for 2026", G_services, pos_stations,label_type=None,filename='basic_tracks_services') #None, ic, all for labels
plotting.plot_degree_histogram(G_tracks,title='Track graph degree histogram')
plotting.plot_degree_histogram(G_services,title='Service graph degree histogram')

# Create track blocks
G_tracks, n_blocks       = dp.create_blocks(G_tracks,num_matching_nodes_required=NUM_MATCHING_NODES_REQUIRED)
plotting.plot_blocks(G_tracks,pos_tracks,strictness=NUM_MATCHING_NODES_REQUIRED,n_blocks=n_blocks)

# Inspect graphs as dataframes
service_nodes, service_edges = sf.graph_to_dataframes(G_services)
infra_nodes, infra_edges = sf.graph_to_dataframes(G_tracks)

# IPV graph
G_ipv = dp.create_ipv_graph(services_ipv, track_nodes) 
plotting.plot_basic_graph(G_ipv,pos_tracks,"IPV Service Graph - 2023~2025",filename='ipv_basic_graph')

# OV Graph
G_ov = dp.create_ov_graph(services_ov,track_nodes)
plotting.plot_basic_graph(G_ov,pos_tracks,"Bus OV Service Graph - planned 2026", label_type=None, filename='ov_basic_graph')
plotting.plot_infrastructure_comparison(G_services,G_ov,pos_stations,label_type=None,plot_tracks=True,filename='services_v_ov_graph',title='Train services vs. line bus services')
plotting.plot_infrastructure_comparison(G_tracks,G_ov,pos_tracks,label_type=None,plot_tracks=True,filename='tracks_v_ov_graph',title='Tracks vs. line bus services')
plotting.plot_graph_edge_attr_greedy(G_ov,pos_stations,attr='route_id',title='Greedy coloring of route_ids',filename='greedy_bus_lines_distinct')
print(f"Finished construction at: {time.strftime('%H:%M:%S')}")


##### RDT data #####
plotting.plot_disruption_heatmap(G_tracks,G_services,pos_tracks,pos_stations,services,target1=TARGET1,target2=TARGET2,print_output=False)
plotting.ipv_services(G_services,pos_stations,None,print_nodes=True)
plotting.plot_rdt_edge_metric(
    G_services,pos_stations,edge_attribute='pct_services_cancelled',
    title='Pct. of Services Disrupted - 2023~2025', colorbar_label='Services disrupted [%]',
    filename='pct_disrupted', label_type=None,print_nodes=False)
plotting.plot_rdt_edge_metric(
    G_services,pos_stations,edge_attribute='max_duration',
    title='Max. Duration of a Disruption [minutes] - 2023~2025', colorbar_label='Max. duration [min]',
    filename='max_disruption_duration', label_type=None,print_nodes=False)
plotting.plot_rdt_edge_metric(
    G_services,pos_stations,edge_attribute='avg_duration',
    title='Avg. Duration of a Disruption [minutes] - 2023~2025', colorbar_label='Avg. duration [min]',
    filename='avg_disruption_duration', label_type=None,print_nodes=False)
plotting.plot_rdt_edge_metric(
    G_services, pos_stations, edge_attribute='historically_disrupted_passengers', 
    title='Disrupted passenger-minutes (TravelersPerDay) - 2023~2025', colorbar_label='Disrupted TravelersPerDay [pax-min]', 
    filename='disrupted_passengers_24hr', label_type=None, print_nodes=False)


##### Demand assignment #####
demand_infra_mixed, demand_infra_model, G_services_demand = demand.flow_assignment(G_tracks,G_services,optimize=ASSIGN_DEMAND,verbose=False, morning_demand=MORNING_DEMAND, decay=DECAY, scale_factor=SCALE_FACTOR)
print(f"Finished demand assignment at: {time.strftime('%H:%M:%S')}")
plotting.demand_flow_comparison(demand_infra_mixed, demand_infra_model, G_services_demand, pos_tracks, pos_stations, None)
plotting.plot_disrupted_pax_minutes(G_services_demand, pos_stations, filename='disrupted_pax_minutes', title='Disrupted passenger-minutes (flow) - 2023~2025') # 24hr demand!

# Overwrite so all later calculations used the morning modeled demand instead of the mixed 24hr flows
if MORNING_DEMAND: G_tracks_demand = demand_infra_model    # model graph contains peak values if morning_demand is passed
else:              G_tracks_demand = demand_infra_mixed    # mixed always contains the 24hr flows from ns where possible

# Inspectable graph as dataframe
nodes_demand, edges_demand = sf.graph_to_dataframes(G_tracks_demand)


############ Analysis ############
##### Disruptions #####
# Edge disruptions
(metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt, 
    metrics_edge_services_no_alternative, metrics_edge_services_ipv_alt, metrics_edge_services_ov_alt) = (
    disruptions.disrupt_edges(G_services_demand, G_tracks_demand, G_ipv, G_ov, run_exp=RUN_EDGE_EXP,morning_demand=MORNING_DEMAND,disrupt_services=True))

# Node disruptions
(metrics_node_tracks_no_alternative, metrics_node_tracks_ipv_alt, metrics_node_tracks_ov_alt, 
    metrics_node_services_no_alternative, metrics_node_services_ipv_alt, metrics_node_services_ov_alt) = (
    disruptions.disrupt_nodes(G_services_demand, G_tracks_demand, G_ipv, G_ov, run_exp=RUN_NODE_EXP,morning_demand=MORNING_DEMAND,disrupt_services=True))

# Block disruptions
(metrics_block_tracks_no_alternative, metrics_block_tracks_ipv_alt, metrics_block_tracks_ov_alt, 
    metrics_block_services_no_alternative, metrics_block_services_ipv_alt, metrics_block_services_ov_alt) = (
    disruptions.disrupt_blocks(G_services_demand, G_tracks_demand, G_ipv, G_ov, run_exp=RUN_BLOCK_EXP, morning_demand=MORNING_DEMAND,disrupt_services=True))

print(f"Finished disruptions at: {time.strftime('%H:%M:%S')}")
# Define which metrics to plot for the different scenarios
tt_metrics   = {'single': ['tt_default', 'tt_alt', 'tt_ipv', 'tt_ov']}
perf_metrics = {'double' : ['APL_u', 'APL_tt', 'APL_ftt', 'APL_flow', 'diameter', 'GE','n_nodes', 'RSGC', 'scaling_factor','avg_degree', 'avg_cluster_coef', 'degree_diversity', 'conductance','natural_connectivity', 'algebraic_connectivity']}
pax_metrics  = {'capacity' : ['disrupted_pax_flow', 'disrupted_pax_min_flow','ipv_capacity', 'delta_ipv_capacity', 'ov_capacity', 'delta_ov_capacity','total_alt_capacity', 'delta_alt_capacity']}

plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_ipv_alt], title='Disruption boxplots for tracks w ipv replacement',group_labels=['tracks w/ ipv'],scaling='zscore',filename='tracks_ipv')
plotting.plot_metric_boxplots(dfs=[metrics_edge_services_ipv_alt], title='Disruption boxplots for services w ipv replacement',group_labels=['services w/ ipv'],scaling='zscore',filename='services_ipv',figsize=(8,6),metric_groups=perf_metrics)
plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_no_alternative], title='Disruption boxplot for track wo replacement',group_labels=['tracks w/o alternatives'],scaling='zscore',filename='tracks_no_alt')
plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_ipv_alt,metrics_edge_services_ipv_alt,metrics_edge_tracks_no_alternative], group_labels=['tracks w/ ipv','services w/ ipv','tracks w/o alternatives'],title='Metric comparison across graph types', scaling='zscore',filename='tracks_services_old')
plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_no_alternative,metrics_edge_tracks_ov_alt,metrics_edge_tracks_ipv_alt], group_labels=['tracks w/o alternatives','tracks / OV','tracks w/ IPV'], title='Comparing metric impacts of edge disruptions to the track graph for different scenarios',scaling='zscore',filename='all_tracks')
plotting.plot_metric_boxplots(dfs=[metrics_edge_services_no_alternative,metrics_edge_services_ov_alt,metrics_edge_services_ipv_alt,], group_labels=['services w/o alternatives','services / OV','services w/ IPV'], title='Comparing metric impacts of edge disruptions to the service graph for different scenarios',scaling='zscore',filename='all_services')

plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_no_alternative,metrics_edge_services_no_alternative], group_labels=['tracks graph','service graph'], title='Comparing impacts of edge disruptions to the track and service graphs',metric_groups=tt_metrics,scaling='zscore',filename='edge_tracks_v_services_no_alt',figsize=(8,6))
plotting.plot_metric_boxplots(dfs=[metrics_block_tracks_no_alternative,metrics_block_services_no_alternative], group_labels=['track graph','service graph'], title='Comparing impacts of block disruptions to the track and service graphs',metric_groups=tt_metrics,scaling='zscore',filename='block_tracks_v_services_no_alt',figsize=(8,6))
plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_no_alternative, metrics_edge_tracks_ov_alt, metrics_edge_tracks_ipv_alt], group_labels=['tracks w/o alternatives','tracks w/ OV','tracks w/ IPV'], title='Comparing metric impacts of edge disruptions to the track graph for different scenarios',metric_groups=perf_metrics,scaling='zscore',filename='edge_tracks',figsize=(16,10))
plotting.plot_metric_boxplots(dfs=[metrics_edge_services_no_alternative, metrics_edge_services_ov_alt, metrics_edge_services_ipv_alt], group_labels=['services w/o alternatives','services w/ OV','services w/ IPV'], title='Comparing metric impacts of edge disruptions to the service graph for different scenarios',metric_groups=perf_metrics,scaling='zscore',filename='edge_services',figsize=(16,10))
plotting.plot_metric_boxplots(dfs=[metrics_block_tracks_no_alternative, metrics_block_tracks_ov_alt, metrics_block_tracks_ipv_alt], group_labels=['blocks w/o alternatives','blocks w/ OV','blocks w/ IPV'], title='Comparing metric impacts of block disruptions to the track graph for different scenarios',metric_groups=perf_metrics,scaling='zscore',filename='block_tracks',figsize=(16,10))
plotting.plot_metric_boxplots(dfs=[metrics_block_services_no_alternative, metrics_block_services_ov_alt, metrics_block_services_ipv_alt], group_labels=['blocks w/o alternatives','blocks w/ OV','blocks w/ IPV'], title='Comparing metric impacts of block disruptions to the service graph for different scenarios',metric_groups=perf_metrics,scaling='zscore',filename='block_services',figsize=(16,10))

plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_no_alternative, metrics_node_tracks_no_alternative, metrics_block_tracks_no_alternative], group_labels=['edge disruptions','node disruptions','block disruptions'], title='Comparing metric impacts of different disruption types to the track graph, no alternative',metric_groups=perf_metrics,scaling='zscore',filename='tracks_disruption_types',figsize=(12,10))
plotting.plot_metric_boxplots(dfs=[metrics_edge_services_no_alternative, metrics_edge_services_ov_alt, metrics_edge_services_ipv_alt], group_labels=['service graph w/o alternatives','service graph w/ line buses','service graph w/ IPV buses'], title='Comparing metric impacts of edge disruptions to the service graph for different replacement scenarios',metric_groups=perf_metrics,scaling='zscore',filename='edge_services_different_replacements',figsize=(12,10))                                  
plotting.plot_metric_boxplots(dfs=[metrics_edge_tracks_ipv_alt,metrics_edge_services_ipv_alt],group_labels=['track graph','service graph'], title='The spread of travel times for the track and service graphs',metric_groups=tt_metrics,scaling='zscore',filename='edges_different_replacements_travel_time',figsize=(7,4))

# Get worst elements from edge disruptions
worst_impacts_edges = metrics.highest_impacts_results(
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt, 
    metrics_edge_services_no_alternative, metrics_edge_services_ipv_alt, metrics_edge_services_ov_alt,disruption_type='edge')


##### Measures #####
# Betweenness #
betweenness_infra, betweenness_service, title1 =  measures.betweenness(G_tracks_demand,G_services_demand,"travel_time")
betweenness_infra_nodes, betweenness_service_nodes, title8 = measures.betweenness_nodes(G_tracks_demand,G_services_demand,"travel_time")

# Eigenvector #
eigen_infra, eigen_service, title2               = measures.eigenvector(G_tracks_demand,G_services_demand,"TravelersPerDay", None)
eigen_infra_none, eigen_service_none, title3     = measures.eigenvector(G_tracks_demand,G_services_demand,None, None)
eigen_infra_weight, eigen_service_weight, title4 = measures.eigenvector(G_tracks_demand,G_services_demand,"TravelersPerDay","flow")

# Closeness #
closeness_infra, closeness_service, title5 = measures.closeness(G_tracks_demand, G_services_demand, "travel_time")

# Pagerank #
pagerank_infra_none, pagerank_service_none, title6      = measures.pagerank(G_tracks_demand, G_services_demand, initial_importance_attr=None, weight_attr=None)
pagerank_infra_weight, pagerank_service_weight, title7  = measures.pagerank(G_tracks_demand, G_services_demand, initial_importance_attr='TravelersPerDay', weight_attr='flow')
pagerank_infra_weight_unnormalized, pagerank_service_weight_unnormalized, title10 = measures.pagerank(G_tracks_demand,G_services_demand, initial_importance_attr='TravelersPerDay', weight_attr='flow',normalize_weights=False)

# Plotting #
plotting.plot_edge_measure(G_tracks, G_services, pos_tracks, pos_stations, betweenness_infra, betweenness_service, title1, filename='edge_betweenness')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, eigen_infra, eigen_service, title2, nodesize_scale=200,filename='node_eigenvector')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, eigen_infra_none, eigen_service_none, title3, nodesize_scale=200,filename='node_eigenvector_none')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, eigen_infra_weight, eigen_service_weight, title4, nodesize_scale=200,filename='node_eigenvector_weight')
plotting.plot_edge_measure(G_tracks, G_services, pos_tracks,pos_stations,sf.map_node_values_to_edges(G_tracks,closeness_infra),sf.map_node_values_to_edges(G_services,closeness_service),title5,filename='edge_closeness')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, pagerank_infra_none, pagerank_service_none, title6, nodesize_scale=10000,filename='node_pagerank_none')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, pagerank_infra_weight, pagerank_service_weight, title7, nodesize_scale=10000,filename='node_pagerank_weight')

plotting.plot_measure(G_services, pos_stations, 'edge', sf.map_node_values_to_edges(G_services_demand,closeness_service), "Service graph closeness centrality (weight = travel_time)", filename='closeness_services_single')
plotting.plot_node_measure(G_tracks, G_tracks, pos_tracks, pos_tracks, eigen_infra_none, eigen_infra_weight, "Track Eigenvector Centrality Comparison", nodesize_scale=200, filename='eigen_infra_comparison',left_subtitle = "a) Eigenvector Centrality (no weight)", right_subtitle = "b) Eigenvector Centrality (weight = flow)",)
plotting.plot_measure(G_services, pos_stations, 'node', pagerank_service_weight, "Service PageRank centrality (weight = flow)", filename='pagerank_services_single', nodesize_scale=10000,)
plotting.plot_measure(G_tracks, pos_tracks, 'edge', betweenness_infra, "Track betweenness centrality (weight = travel_time)", filename='betweenness_infra_single')
plotting.plot_node_measure(G_tracks, G_services, pos_tracks, pos_stations, eigen_infra_weight, eigen_service_weight, "Unnormalized eigenvector centrality (weight = flow) ", nodesize_scale=200, filename='eigenvector_unnormalzied_with_flow_weight',left_subtitle = "a) track graph", right_subtitle = "b) service graph",)

# Collect measures
measures_edges_infra = {
    "betweenness_infra"     : betweenness_infra,
    "eigen_infra_none"      : sf.map_node_values_to_edges(G_tracks_demand,eigen_infra_none),
    "eigen_infra_weight"    : sf.map_node_values_to_edges(G_tracks_demand,eigen_infra_weight),
    "closeness_infra"       : sf.map_node_values_to_edges(G_tracks_demand,closeness_infra),
    "pagerank_infra"        : sf.map_node_values_to_edges(G_tracks_demand,pagerank_infra_none),
}

measures_edges_services = {
    "betweenness_service"   : betweenness_service,
    "eigen_service_none"    : sf.map_node_values_to_edges(G_services_demand,eigen_service_none),
    "eigen_service_weight"  : sf.map_node_values_to_edges(G_services_demand,eigen_service_weight),
    "closeness_service"     : sf.map_node_values_to_edges(G_services_demand,closeness_service),
    "pagerank_service"      : sf.map_node_values_to_edges(G_services_demand,pagerank_service_none),
}

measures_nodes_infra = {
    'betweenness_infra'     : betweenness_infra_nodes,
    'eigen_infra_none'      : eigen_infra_none,
    'eigen_infra_weight'    : eigen_infra_weight,
    'closeness_infra'       : closeness_infra,
    'pagerank_infra'        : pagerank_infra_weight,
}

measures_nodes_services = {
    'betweenness_services'  : betweenness_service_nodes,
    'eigen_service_none'    : eigen_service_none,
    'eigen_service_weight'  : eigen_service_weight,
    'closeness_service'     : closeness_service,
    'pagerank_service'      : pagerank_service_weight,
}

measures_blocks_infra = {
    'betweenness_infra'     : sf.map_node_values_to_blocks(G_tracks_demand,betweenness_infra_nodes),
    'eigen_infra_none'      : sf.map_node_values_to_blocks(G_tracks_demand,eigen_infra_none),
    'eigen_infra_weight'    : sf.map_node_values_to_blocks(G_tracks_demand,eigen_infra_weight),
    'closeness_infra'       : sf.map_node_values_to_blocks(G_tracks_demand,closeness_infra),
    'pagerank_infra'        : sf.map_node_values_to_blocks(G_tracks_demand,pagerank_infra_none),
}

measures_blocks_services = {
    'betweenness_services'  : sf.map_node_values_to_blocks(G_tracks_demand,betweenness_service_nodes),
    'eigen_service_none'    : sf.map_node_values_to_blocks(G_tracks_demand,eigen_service_none),
    'eigen_service_weight'  : sf.map_node_values_to_blocks(G_tracks_demand,eigen_service_weight),
    'closeness_service'     : sf.map_node_values_to_blocks(G_tracks_demand,closeness_service),
    'pagerank_service'      : sf.map_node_values_to_blocks(G_tracks_demand,pagerank_service_none),
}

plotting.plot_measure_boxplots([betweenness_infra,betweenness_service,betweenness_infra_nodes,betweenness_service_nodes,measures_blocks_infra['betweenness_infra'],measures_blocks_services['betweenness_services']],['Edge tracks', 'Edge services', 'Node tracks','Node services','Block tracks','Block services'],scaling='none', title='Comparison of betweeness centrality',filename='betweenness_comparison',figsize=(5,4))

plotting.plot_measure_boxplots([betweenness_infra,eigen_infra_none,eigen_infra_weight,closeness_infra,pagerank_infra_none,pagerank_infra_weight],['Betweenness','Eigenvector (unweighted)','Eigenvector (weighted)','Closeness','PageRank (unweighted)','PageRank (weighted)'],scaling='zscore',title='Comparison of different measures for the track graph',filename='track_measure_comparison_zscore',figsize=(5,4))
plotting.plot_measure_boxplots([betweenness_infra,eigen_infra_none,eigen_infra_weight,closeness_infra,pagerank_infra_none,pagerank_infra_weight],['Betweenness','Eigenvector (unweighted)','Eigenvector (weighted)','Closeness','PageRank (unweighted)','PageRank (weighted)'],scaling='none',title='Comparison of different measures for the track graph',filename='track_measure_comparison',figsize=(5,4))
plotting.plot_measure_boxplots([closeness_infra,pagerank_infra_none,pagerank_infra_weight],['Closeness','PageRank (unweighted)','PageRank (weighted)'],scaling='none',title='Comparison of Closeness and PageRank measure values',filename='measure_detailed_comparison',figsize=(5,4))

plotting.plot_measure_boxplots(
    {'a) 1st series': [betweenness_infra, eigen_infra_none, eigen_infra_weight],
     'b) 2nd series': [closeness_infra, pagerank_infra_none, pagerank_infra_weight]},
    {'a) 1st series': ['Betweenness', 'Eigen (none)', 'Eigen (flow)'],
     'b) 2nd series': ['Closeness', 'PageRank (none)', 'PageRank (flow)']},
      scaling='none',title='Track measure comparison',filename='track_measure_comparison',figsize=(6,5))

##### Metric v Measure correlation #####
### Edge correlations ###
# Tracks
correlations_edges_tracks_no_alt    = disruptions.correlation_calc(metrics=metrics_edge_tracks_no_alternative, measures=measures_edges_infra, filename='correlation_edges_tracks_no_alt', run_correlation=RUN_EDGE_EXP)
correlations_edges_tracks_ipv_alt   = disruptions.correlation_calc(metrics=metrics_edge_tracks_ipv_alt, measures=measures_edges_infra, filename='correlation_edges_tracks_ipv_alt', run_correlation=RUN_EDGE_EXP)
correlations_edges_tracks_ov_alt    = disruptions.correlation_calc(metrics=metrics_edge_tracks_ov_alt, measures=measures_edges_infra, filename='correlation_edges_tracks_ov_alt', run_correlation=RUN_EDGE_EXP)

# Services
correlations_edges_services_no_alt  = disruptions.correlation_calc(metrics=metrics_edge_services_no_alternative, measures=measures_edges_services, filename='correlation_edges_services_no_alt', run_correlation=RUN_EDGE_EXP)
correlations_edges_services_ipv_alt = disruptions.correlation_calc(metrics=metrics_edge_services_ipv_alt, measures=measures_edges_services, filename='correlation_edges_services_ipv_alt', run_correlation=RUN_EDGE_EXP)
correlations_edges_services_ov_alt  = disruptions.correlation_calc(metrics=metrics_edge_services_ov_alt, measures=measures_edges_services, filename='correlation_edges_services_ov_alt', run_correlation=RUN_EDGE_EXP)

### Node correlations ###
# Tracks
correlations_nodes_tracks_no_alt    = disruptions.correlation_calc(metrics=metrics_node_tracks_no_alternative, measures=measures_nodes_infra, filename='correlation_nodes_tracks_no_alt', run_correlation=RUN_NODE_EXP)
correlations_nodes_tracks_ipv_alt   = disruptions.correlation_calc(metrics=metrics_node_tracks_ipv_alt, measures=measures_nodes_infra, filename='correlation_nodes_tracks_ipv_alt', run_correlation=RUN_NODE_EXP)
correlations_nodes_tracks_ov_alt    = disruptions.correlation_calc(metrics=metrics_node_tracks_ov_alt, measures=measures_nodes_infra, filename='correlation_nodes_tracks_ov_alt', run_correlation=RUN_NODE_EXP)

# Services
correlations_nodes_services_no_alt  = disruptions.correlation_calc(metrics=metrics_node_services_no_alternative, measures=measures_nodes_services, filename='correlation_nodes_services_no_alt', run_correlation=RUN_NODE_EXP)
correlations_nodes_services_ipv_alt = disruptions.correlation_calc(metrics=metrics_node_services_ipv_alt, measures=measures_nodes_services, filename='correlation_nodes_services_ipv_alt', run_correlation=RUN_NODE_EXP)
correlations_nodes_services_ov_alt  = disruptions.correlation_calc(metrics=metrics_node_services_ov_alt, measures=measures_nodes_services, filename='correlation_nodes_services_ov_alt', run_correlation=RUN_NODE_EXP)

### Block correlations ###
# Tracks
correlations_blocks_tracks_no_alt   = disruptions.correlation_calc(metrics=metrics_block_tracks_no_alternative, measures=measures_blocks_infra, filename='correlation_blocks_tracks_no_alt', run_correlation=RUN_BLOCK_EXP)
correlations_blocks_tracks_ipv_alt  = disruptions.correlation_calc(metrics=metrics_block_tracks_ipv_alt, measures=measures_blocks_infra, filename='correlation_blocks_tracks_ipv_alt', run_correlation=RUN_BLOCK_EXP)
correlations_blocks_tracks_ov_alt   = disruptions.correlation_calc(metrics=metrics_block_tracks_ov_alt, measures=measures_blocks_infra, filename='correlation_blocks_tracks_ov_alt', run_correlation=RUN_BLOCK_EXP)  

# Services
correlations_blocks_services_no_alt  = disruptions.correlation_calc(metrics=metrics_block_services_no_alternative, measures=measures_blocks_services, filename='correlation_blocks_services_no_alt', run_correlation=RUN_BLOCK_EXP)
correlations_blocks_services_ipv_alt = disruptions.correlation_calc(metrics=metrics_block_services_ipv_alt, measures=measures_blocks_services, filename='correlation_blocks_services_ipv_alt', run_correlation=RUN_BLOCK_EXP)
correlations_blocks_services_ov_alt  = disruptions.correlation_calc(metrics=metrics_block_services_ov_alt, measures=measures_blocks_services, filename='correlation_blocks_services_ov_alt', run_correlation=RUN_BLOCK_EXP)

# Plot correlations
plotting.plot_correlations(correlations_edges_tracks_ipv_alt, title='Infra ipv correlations - edges',filename='edge_track_ipv_correlations')
plotting.plot_correlations(correlations_edges_services_ipv_alt, title='Service ipv correlations - edges',filename='edge_service_ipv_correlations')
plotting.plot_correlations(correlations_edges_tracks_no_alt, title='Infra correlations without replacement - edges',filename='edge_tracks_no_alt_correlations')
plotting.plot_correlations(correlations_nodes_services_no_alt, title='Service correlations without replacement - nodes',filename='nodes_services_no_alt_correlations')
plotting.plot_correlations(correlations_nodes_tracks_no_alt, title='Infra correlations without replacement - nodes',filename='nodes_tracks_noreplacement')

plotting.plot_correlations(correlations_edges_tracks_no_alt, metric_groups=perf_metrics, title='Track correlations without replacement, performance metrics - edge disruptions',filename='edges_tracks_noreplacement_double_metrics')
plotting.plot_correlations(correlations_edges_services_no_alt, metric_groups=perf_metrics, title='Service correlations without replacement, performance metrics - edge disruptions',filename='edges_services_noreplacement_double_metrics')
plotting.plot_correlations(correlations_blocks_tracks_no_alt, metric_groups=perf_metrics, title='Track correlations without replacement, performance metrics - block disruptions',filename='blocks_tracks_noreplacement_double_metrics',figsize=(10,6))
plotting.plot_correlations(correlations_blocks_services_no_alt, metric_groups=perf_metrics, title='Service correlations without replacement, performance metrics - block disruptions',filename='blocks_services_noreplacement_double_metrics',figsize=(10,6))
plotting.plot_correlations(correlations_edges_services_ipv_alt, metric_groups=pax_metrics, title='Service correlations with IPV replacement, passenger metrics - edge disruptions',filename='edges_services_ipv_capacity_metrics',figsize=(7,3))
plotting.plot_correlations(correlations_blocks_services_ov_alt, metric_groups=tt_metrics, title='Service correlations with line bus replacement, travel time metrics - block disruptions',filename='blocks_services_ov_tt_metrics',figsize=(10,6))

plotting.plot_correlations(correlations_nodes_tracks_no_alt, metric_groups=perf_metrics, title='Node correlations without replacement, performance metrics - node disruptions', filename='nodes_tracks_noreplacement_double_metrics',figsize=(10,6))

##### Interventions #####
# Nedersaksenlijn
(nodes_new_neder, edges_new_neder, betweenness_new_neder,
    targeted_no_alt_neder, targeted_ipv_alt_neder, targeted_ov_alt_neder,
    diff_no_alt_neder, diff_ipv_alt_neder, diff_ov_alt_neder) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['nedersaksenlijn'],scenario_name='nedersaksenlijn',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Lelylijn (no extension)
(nodes_new_lely, edges_new_lely, betweenness_new_lely,
    targeted_no_alt_lely, targeted_ipv_alt_lely, targeted_ov_alt_lely,
    diff_no_alt_lely, diff_ipv_alt_lely, diff_ov_alt_lely) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['lelylijn'],scenario_name='lelylijn',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Lelylijn (with extension)
(nodes_new_lely_extension, edges_new_lely_extension, betweenness_new_lely_extension,
    targeted_no_alt_lely_extension, targeted_ipv_alt_lely_extension, targeted_ov_alt_lely_extension,
    diff_no_alt_lely_extension, diff_ipv_alt_lely_extension, diff_ov_alt_lely_extension) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['lelylijn_extension','lelylijn'],scenario_name='lelylijn_w_extension',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Nedersaksenlijn + Lelylijn (unextended)
(nodes_new_neder_lely, edges_new_neder_lely, betweenness_new_neder_lely,
    targeted_no_alt_neder_lely, targeted_ipv_alt_neder_lely, targeted_ov_alt_neder_lely,
    diff_no_alt_neder_lely, diff_ipv_alt_neder_lely, diff_ov_alt_neder_lely) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['nedersaksenlijn','lelylijn'],scenario_name='nedersaksenlijn_w_lelylijn',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Nedersaksenlijn + Lelylijn (extended)
(nodes_new_neder_lely_extension, edges_new_neder_lely_extension, betweenness_new_neder_lely_extension,
    targeted_no_alt_neder_lely_extension, targeted_ipv_alt_neder_lely_extension, targeted_ov_alt_neder_lely_extension,
    diff_no_alt_neder_lely_extension, diff_ipv_alt_neder_lely_extension, diff_ov_alt_neder_lely_extension) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['nedersaksenlijn','lelylijn','lelylijn_extension'],scenario_name='nedersaksenlijn_w_lelylijn_extension',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Nedersaksenlijn + Lelylijn (extended) + Afsluitdijk
(nodes_new_neder_lely_extension_afsluitdijk, edges_new_neder_lely_extension_afsluitdijk, betweenness_new_neder_lely_extension_afsluitdijk,
    targeted_no_alt_neder_lely_extension_afsluitdijk, targeted_ipv_alt_neder_lely_extension_afsluitdijk, targeted_ov_alt_neder_lely_extension_afsluitdijk,
    diff_no_alt_neder_lely_extension_afsluitdijk, diff_ipv_alt_neder_lely_extension_afsluitdijk, diff_ov_alt_neder_lely_extension_afsluitdijk) = interventions.run_intervention_scenario(
    G_tracks_demand,G_services_demand,G_ipv,G_ov,pos_tracks,
    metrics_edge_tracks_no_alternative, metrics_edge_tracks_ipv_alt, metrics_edge_tracks_ov_alt,
    trajects=['nedersaksenlijn','lelylijn', 'lelylijn_extension','afsluitdijk'],scenario_name='nedersaksenlijn_w_lelylijn_extension_afsluitdijk',
    target1=TARGET1,target2=TARGET2,morning_demand=MORNING_DEMAND,decay=DECAY,scale_factor=SCALE_FACTOR,old_track_betweenness=betweenness_infra)

# Get end time
total_time = time.time() - start_time
print(f"Script finished at: {time.strftime('%H:%M:%S')}, started at: {time.strftime('%H:%M:%S', time.gmtime(start_time))}. Total: {time.strftime('%H:%M:%S', time.gmtime(total_time))}")

# Close db connection
dp.pg_close() 
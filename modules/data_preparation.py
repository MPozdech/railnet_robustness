import os
import psycopg                              # type: ignore
import pandas as pd                         # type: ignore
import json
import numpy as np                          # type: ignore
from geopy.distance import geodesic         # type: ignore
import networkx as nx                       # type: ignore
from collections import Counter, defaultdict
import modules.supporting_functions as sf   # type: ignore
import warnings

"""
This handles everything to load, clean, and join the data from the raw versions to
those that create the (un-)directed graphs
"""

# Suppress message about using SQLAlchemy
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable.*"
)

# Connect to db
conn = psycopg.connect(
    host=os.environ["PGHOST"],  
    port=int(os.environ["PGPORT"]),
    dbname=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"]
)

cur = conn.cursor()

def pg_close():
    cur.close()
    conn.close()

def pg_import(table: str) -> pd.DataFrame:
    """
    Imports a table or query result from PostgreSQL.
    
    Input is either:
            - 'table_name'        (searches all schemas)
            - 'schema.table_name' (explicit schema)
            -  A raw SQL query
    Returns DataFrame of the result.
    """
    # Raw SQL query path
    if table.strip().upper().startswith("SELECT"):
        query = table.strip()
        if not query.endswith(";"):
            query += ";"
        try:
            return pd.read_sql(query, conn)
        except Exception as e:
            print(f"Error executing query: {e}")
            return None

    # Table name path
    parts = table.split(".")

    if len(parts) == 2:
        schema, table_name = parts
        query = f"SELECT * FROM {schema}.{table_name};"

    elif len(parts) == 1:
        check_query = """
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_name = %s;
        """
        matches = pd.read_sql(check_query, conn, params=(parts[0],))
        if matches.empty:
            print(f"No table named '{table}' found.")
            return None
        if len(matches) > 1:
            print(f"Multiple tables found: {matches[['table_schema','table_name']].to_string(index=False)}. Schema?.")
            return None
        schema = matches.iloc[0]["table_schema"]
        table_name = matches.iloc[0]["table_name"]
        query = f"SELECT * FROM {schema}.{table_name};"

    else:
        print(f"Invalid table format: '{table}'. Use 'table', 'schema.table', or a SELECT query.")
        return None

    try:
        return pd.read_sql(query, conn)
    except Exception as e:
        print(f"Error fetching '{table}': {e}")
        return None


def json_import(path: str):
    """
    Imports the stations_df (nodes) and segments_df (edges) json data from the NS dashboard.
    This is the basis for the track graph.

    Returns the dataframes for each.
    """

    with open(sf.get_dir(path), "r", encoding="utf-8") as f:
        ns_data = json.load(f)
    
    # This converts the 1st top level of the json into a df for the data attached to the station nodes
    demand = ns_data["Stations"] 
    rows = []
    for station in demand:
        coord = station.get("Coordinate") or {}

        # Information about each station
        base = {
            "Alias" : station.get("Alias"),
            "Name"  : station.get("Name"),
            "Lat"   : coord.get("Lat"),
            "Lng"   : coord.get("Lng"),
            "Type"  : station.get("Type"),
            "Size"  : station.get("Size"),
        }

        # Here the BoardingDeboarding demand values are stored. 
        data_dict = {
            item["ClientKey"]: item["Value"]
            for item in station.get("Data", [])
        }

        base.update(data_dict)
        rows.append(base)

    stations_df = pd.DataFrame(rows) 

    #### Making things consistent ####
    # Renaming so GTFS names match RDT names
    stations_df.loc[stations_df['Name'] == 'Alphen aan den Rijn', 'Name']    = 'Alphen a/d Rijn'
    stations_df.loc[stations_df['Name'] == "Harde ‘t", 'Name']               = "'t Harde"
    stations_df.loc[stations_df['Name'] == "Den Haag Laan van NOI", 'Name']  = "Den Haag Laan v NOI"
    stations_df.loc[stations_df['Name'] == "Breda Prinsenbeek", 'Name']      = "Breda-Prinsenbeek"
    stations_df.loc[stations_df['Name'] == "'s-Hertogenbosch  Oost", 'Name'] = "'s-Hertogenbosch Oost"
    stations_df.loc[stations_df['Name'] == "Houthem-St.Gerlach", 'Name']     = "Houthem-St. Gerlach"
    stations_df.loc[stations_df['Name'] == "Boven Hardinxveld", 'Name']      = "Boven-Hardinxveld"
    
    # Set yard type -- these are dead ends that are pointless for the analysis and are ignored
    stations_df.loc[stations_df['Name'] == 'Lelystad Opstel', 'Type']               = 'yard'
    stations_df.loc[stations_df['Name'] == 'Hoorn Kersenboogerd Opstel', 'Type']    = 'yard'
    stations_df.loc[stations_df['Name'] == 'Amsterdam Lijnwerkplaats Zuid', 'Type'] = 'yard'
    stations_df.loc[stations_df['Name'] == 'Watergraafsmeer', 'Type']               = 'yard'
    stations_df.loc[stations_df['Name'] == 'Hoofddorp Opstel', 'Type']              = 'yard'
    stations_df.loc[stations_df['Name'] == 'Bokkeduinen', 'Type']                   = 'yard'

    # Set closed station type -- these stations lie on the tracks but do not see service anymore
    stations_df.loc[stations_df['Name'] == 'Heerlen de Kissel', 'Type']  = 'closed'
    stations_df.loc[stations_df['Name'] == 'Sappemeer Oost', 'Type']     = 'closed'
    stations_df.loc[stations_df['Name'] == 'Woerden Molenvliet', 'Type'] = 'closed'

    # Add stations that were missing
    zlhs = pd.DataFrame({"Alias": ['ZLSH'], "Name": ["Zwolle Stadshagen"], "Lat": 52.52764, "Lng": 6.051313, "Type": 'other'}) # This station was missing
    bdgr = pd.DataFrame({"Alias": ['BDGR'], "Name": ["Breda grens"], "Lat": 51.4910679088267, "Lng": 4.73648676514939, "Type": 'border'})
    nscg = pd.DataFrame({"Alias": ['NSCG'], "Name": ["NSC grens"], "Type": 'border'})
    odzg = pd.DataFrame({"Alias": ['ODZG'], "Name": ["Oldenzaal grens"], "Type": 'border'})
    zvg  = pd.DataFrame({"Alias": ['ZVG'], "Name": ["Zeevenaar grens"], "Type": 'border'})
    rsdg = pd.DataFrame({"Alias": ['RSDG'], "Name": ["Roosendaal grens"], "Type": 'border'})
    vlgr = pd.DataFrame({"Alias": ['VLGR'], "Name": ["Venlo grens"], "Type": 'border'})
    edng = pd.DataFrame({"Alias": ['EDNG'], "Name": ["EDNG grens"], "Type": 'border'})
    gg   = pd.DataFrame({"Alias": ['GG'], "Name": ["Gronau grens"], "Type": 'border'})
    hzg  = pd.DataFrame({"Alias": ['HZG'], "Name": ["HZG grens"], "Type": 'border'})

    stations_df = pd.concat([stations_df, zlhs,bdgr,nscg,odzg,zvg,rsdg,vlgr,edng,gg,hzg], ignore_index=True)

    # This loads the data associated with segments
    segments = ns_data["Segments"] 
    rows = []
    for seg in segments:
        row = {
            "from_alias": seg["A"]["StationAlias"],
            "from_lat": seg["A"]["Coordinate"]["Lat"],
            "from_lng": seg["A"]["Coordinate"]["Lng"],
            "from_travelers": seg["A"]["Travelers"],

            "to_alias": seg["B"]["StationAlias"],
            "to_lat": seg["B"]["Coordinate"]["Lat"],
            "to_lng": seg["B"]["Coordinate"]["Lng"],
            "to_travelers": seg["B"]["Travelers"],

            "thickness": seg["Thickness"],
            "length": seg["Length"], #not real lenght
        }

        rows.append(row)

    segments_df = pd.DataFrame(rows) 

    # This edge was missing due to stadtshagen node missing
    kpn = pd.DataFrame({"from_alias": ['ZLSH'], "from_lat": 52.52764, "from_lng": 6.051313, "to_alias": ['KPN'], "to_lat": 52.5596738671398, "to_lng": 5.92172766076232}) # Missing station
    segments_df = pd.concat([segments_df, kpn], ignore_index=True)
    
    return stations_df, segments_df

def make_edge_key(df: pd.DataFrame, src: str, dst: str) -> pd.DataFrame:
    """Add a canonical undirected edge key to any DataFrame with directed edges."""
    df['PK'] = [
        tuple(sorted((a, b)))
        for a, b in zip(df[src].fillna("none"), df[dst].fillna("none"))
    ]
    df.set_index(['PK'], inplace=True, drop=False)
    return df

def agg_dicts(series):
    """Aggregates values in dicts per key."""
    total = Counter()
    for d in series.dropna():
        total.update(d)
    return dict(total)

def segment_joining(segments_df: object, stations_df: object, node_pairs: object, ipv_services:object, ov_services:object,ipv_capacity:int = 50, ov_capacity:int=90,headway:int=30) -> object:
    """
    This connects all of prior tables into one dataframe,
    which is based on the segments_df table from NS.

    A primary_key value is given to every node that is used for all subsequent joins.
    """
    # Join "from" stations, as all NS stations have a from_alias but not all to_alias connect to a from_alias
    print("Constructing track edgelist")
    segments_joined = segments_df.merge(
        stations_df[[
            "Alias",
            "Name",
        ]],
        how="left", # The segments are the primary key for this table.
        left_on="from_alias",
        right_on="Alias",
        suffixes=('_to','_from')
    )

    # Join "to" stations
    segments_joined = segments_joined.merge(
        stations_df[[
            "Alias",
            "Name",
        ]],
        how="left",
        left_on="to_alias",
        right_on="Alias",
        suffixes=('_from','_to')
    )

    # Assign the edge PK
    segments_joined = make_edge_key(segments_joined, src="Name_from",dst="Name_to")

    # Get avg TT and total disruption count from service table
    service_data = (
        node_pairs[['travel_time']]
        .groupby(node_pairs.index)
        .agg({
            "travel_time": "mean",
        })
    )

    # Join travel times from services to tracks
    segments_joined = segments_joined.merge(
        service_data,
        how='left',
        left_index=True,
        right_index=True,
    )

    segments_joined["geo_length"] = segments_joined.apply(
        lambda row: geodesic(
            (row["from_lat"], row["from_lng"]),
            (row["to_lat"], row["to_lng"])
        ).km,
        axis=1
    )

    # Fit travel times for edges with an unknown TT using the speed of the known-TT edge whose geo_length is closest
    segments_joined['speed'] = segments_joined["geo_length"] / segments_joined["travel_time"]  #km/min

    known_mask = segments_joined['travel_time'].notna()
    unknown_mask = ~known_mask

    if unknown_mask.any():
        # merge_asof needs both sides sorted on the match column
        known_by_length = segments_joined.loc[known_mask, ['geo_length', 'speed']].sort_values('geo_length')
        unknown_by_length = segments_joined.loc[unknown_mask, ['geo_length']].sort_values('geo_length')

        nearest = pd.merge_asof(
            unknown_by_length, known_by_length,
            on='geo_length', direction='nearest',
        )
        nearest.index = unknown_by_length.index  # merge_asof drops the original row labels - restore them for .loc alignment below

        segments_joined.loc[nearest.index, 'speed'] = nearest['speed'].values
        segments_joined.loc[nearest.index, 'travel_time'] = round(
            segments_joined.loc[nearest.index, 'geo_length'] / segments_joined.loc[nearest.index, 'speed'], 1
        )

    #### IPV data joining ####
    ipv_data = (
        ipv_services[['p85_max_travel_time_minutes','total_services','service_type_breakdown','avg_headway_minutes']] 
        .groupby(ipv_services.index)
        .agg({
            'p85_max_travel_time_minutes': "mean",
            'total_services'             : "sum",
            'avg_headway_minutes'        : "min",
            'service_type_breakdown'     : agg_dicts,
        })
    )

    segments_joined = segments_joined.merge(
        ipv_data,
        how='left',
        left_index=True,
        right_index=True,
    )

    # Drop unnecessary columns
    segments_joined.drop(labels=[
        'thickness',
        'Alias_from',
        'Alias_to',
        'length',
        'from_alias',
        'to_alias',
    ], axis=1, inplace=True)

    # Assume that any edge without registered capacity had the constant headway
    segments_joined['avg_headway_minutes'] = segments_joined['avg_headway_minutes'].fillna(headway)

    # The capacity is for both directions since undirected
    segments_joined['capacity'] = round((120 / segments_joined['avg_headway_minutes']) * ipv_capacity * 2)

    # Flow across a link is pax going both towards a node and away from a node since this data is on an undirected graph
    segments_joined["real_flow"] = round(segments_joined["to_travelers"] + segments_joined["from_travelers"],0)
    segments_joined[["real_flow"]] = segments_joined[["real_flow"]].fillna(0)

    segments_joined['ipv_speed'] = segments_joined.apply(lambda row : row["geo_length"] / row["p85_max_travel_time_minutes"] if row["p85_max_travel_time_minutes"] > 0 else None, axis=1)


    #### OV joining ####
    ov_data = ov_services[['travel_time_ov_min','avg_peak_headway_min']].groupby(ov_services.index).agg({'travel_time_ov_min' : "max",'avg_peak_headway_min': "min"})

    ov_data['avg_peak_headway_min'] = ov_data['avg_peak_headway_min'].fillna(headway)
    ov_data[['ov_capacity']] = round((120 / ov_data[['avg_peak_headway_min']]) * ov_capacity * 2,0)

    segments_joined = segments_joined.merge(
        ov_data,
        how='left',
        left_index=True,
        right_index=True,
    )

    # Better ordering and renamed
    segments_joined = segments_joined[["travel_time","p85_max_travel_time_minutes",'travel_time_ov_min',"real_flow","total_services","service_type_breakdown",'from_lat','from_lng','to_lat','to_lng','Name_from','Name_to','geo_length','speed','ipv_speed']].rename(columns={
        "p85_max_travel_time_minutes" : "ipv_travel_time",
        "total_services"              : "ipv_services_count",
        "service_type_breakdown"      : "ipv_service_types",
    })

    return segments_joined

def stations_joining(stations_df: object, stations: object, ov_24: object, catchments: object, export: bool) -> object:
    """
    Connects the stations (RDT) table and the OV Oost demand tables to the NS stations table.
    Also fits the TravelersPerDay value if none is available from the either datasets.
    """

    print("Merging node attributes")
    #### Fixing IC markers to be more useful #####
    # Stations which either do not see IC services stop, or do not have switches to enable return trips, or are too close to larger stations
    non_ic_stations = [
        'Bovenkarspel Flora',
        'Bovenkarspel Grootebroek',
        'Hoorn Kersenboogerd',
        'Diemen Zuid',
        'Amsterdam Muiderpoort',
        'Amsterdam RAI',
        'Den Haag Mariahoeve',
        'Alphen a/d Rijn',
        'Rotterdam Stadion',
        'Vlissingen Souburg',
        'Middelburg',
        'Arnemuiden',
        'Kapelle-Biezelinge',
        'Kruiningen-Yerseke',
        'Krabbendijke',
        'Rilland-Bath',
        'Etten-Leur',
        'Deurne',
        'Horst-Sevenum',
        'Meerssen',
        'Den Helder Zuid',
        'Emmen Zuid',
        'Alkmaar Noord',
        'Heemstede-Aerdenhout',
        'Heiloo',
        'Castricum',
        'Dalfsen',                  # Only one side switch
        'Hardenberg',               # Too close to Mariënberg that has a switch to the Zwolle / Almelo line
        'Amersfoort Schothorst',    # Only sees IC Direct services, also too close to A'foort Centraal
        'Veenendaal-De Klomp'       # Too close to Ede-Wagenigen, only sees some IC services stop
    ]
    stations.loc[stations["name_long"].isin(non_ic_stations), "ic_station"] = False # These are not valid termini for services

    # These stations do not see IC services stop but are large enough to reasonably be nodes for blocks
    # Also those that are termini stations but not border nodes! 
    ic_stations = [
        'Uitgeest',         # Large enough to be IC, also switch between two lines
        'Geldermalsen',     # Large enough to be Ic, degree = 4
        'Harlingen Haven',  # k = 1
        'Stavoren',         # k = 1
        'Roodeschool',      # k = 1
        'Delfzijl',         # k = 1
        'Bad Nieuweschans', # k = 1
        'Oldenzaal',        # k = 1
        'Glanerbrug',       # k = 1
        'Winterswijk',      # k = 2 BUT if excluded would ignore the entirity of this entire branchline
        'Rhenen',           # k = 1
        'Kampen',           # k = 1
        'Veendam',          # k = 1
        'Zandvoort aan Zee',# k = 1
        'Eijsden',          # k = 1
        'Kerkrade Centrum', # k = 1
        'Eygelshoven Markt',# k = 1
        'Boxtel',           # k = 3, also I experienced a SPR service stopping here when Den Bosch - Boxtel was disrupted
        'Lage Zwaluwe',     # k = 4, otherwise very large disruptions due to HSL. Larger station as well
        'Woerden',          # k = 4, otherwise very large disruptions due switches.
        'Breda High Speed aansluiting', # Caused everything from Breda to R'dam be disrupted, too large
        'Rotterdam Lombardijen', # Caused excessive disruptions due to HSL connection, also large station w/ k = 3 -> actually should be Barendrecht but bad representation in JSON.
        'Den Dolder', # k = 3 
    ]
    stations.loc[stations["name_long"].isin(ic_stations), "ic_station"] = True

    # Merge the RDT stations to the NS stations (nodes)
    stations_df = stations_df.merge(
        stations[[
            "name_long",
            "country",
            "ic_station",
        ]],
        left_on='Name',
        right_on='name_long',
        how='left'
    )

    stations_df['ic_station'] = stations_df['ic_station'].fillna(False)

    # Merge the ov_oost demand
    stations_df = stations_df.merge(
        ov_24[[
            "station",
            "reizigers_station",
        ]],
        how='left',
        left_on='Name',
        right_on='station'
    )

    # Add the demands together
    cols_demand = ["BoardingDeboarding", "reizigers_station"] # Adding "Transfering" here would include it in the demand calculation 
    cols_total  = ["BoardingDeboarding", "reizigers_station", "Transfering"]
    stations_df["demand"] = stations_df[cols_demand].sum(axis=1).where(stations_df[cols_demand].notna().any(axis=1))
    stations_df["TravelersPerDay"] = stations_df[cols_total].sum(axis=1).where(stations_df[cols_total].notna().any(axis=1))

    # If station is full NS OR is partial/non-ns BUT I have demand data from OV Oost then print true to station row
    stations_df["full_demand"] = (
        (stations_df["Type"] == "ns") & (stations_df["TravelersPerDay"].notna())
    ) | (
        (stations_df["Type"].isin(["ns-other", "other"])) & (stations_df["reizigers_station"].notna())
    )

    # Merge the population catchments
    stations_df = stations_df.merge(
        catchments[["name_long","station_catchment"]],
        how='left',
        left_on='Name',
        right_on='name_long'
    )

    # Use fitted values to add station demand for stations with no ridership data available. 
    stations_df["TravelersPerDay"] = stations_df["TravelersPerDay"].fillna(
        0.325 * stations_df["station_catchment"] ** 0.941 # exponential equation from excel fitting
    )

    # Use median % in peak hours to fit values for stations without known %
    stations_df["MorningRush"] = stations_df["MorningRush"].fillna( 
        28
    )

    # Use MorningRush % to get morning demand, prefer demand values over (fitted) TravelersPerDay
    stations_df["MorningDemand"] = (
        round(stations_df["demand"].fillna(stations_df["TravelersPerDay"]) * (stations_df["MorningRush"]/100),0)
    )

    if export:
        population_catchment = stations_df[[
                "Alias",
                "Name",
                "Type",
                "TravelersPerDay",
                "BoardingDeboarding",
                "Transfering",
                "reizigers_station",
                "demand",
                "full_demand",
                "station_catchment",
                "MorningRush",
                "MorningDemand",
                "EveningRush",
                "LowTime"
            ]]
        
        population_catchment.to_csv(sf.get_dir("export/pop_catchments.csv"))

    # Drop unnecessary columns
    stations_df.drop(labels=[
        'name_long_x',
        'name_long_y',
        'station',
        'PreWalking',
        'PreBicycle',
        'PreCarDriver',
        'PreCarPassenger',
        'PreBTM',
        'PreTaxi',
        'PostWalking',
        'PostBicycle',
        'PostCarDriver',
        'PostCarPassenger',
        'PostBTM',
        'PostTaxi',
        'Percentage7Plus',
        'Alias',
        'EveningRush',
        'LowTime',
        'station_catchment',
    ], axis=1, inplace=True) # Drop the joined cols

    stations_df.set_index(["Name"],inplace=True)

    # Better ordering
    stations_df = stations_df[["TravelersPerDay","demand","reizigers_station","BoardingDeboarding","Transfering","MorningDemand","MorningRush","Type","Lat","Lng",'ic_station']]

    return stations_df

def node_pairs_joining(node_pairs: object, track_nodes: object, disrupted_services: object, disruption_durations: pd.DataFrame, ipv_services:object,ov_services:object,ipv_capacity:int=50,ov_capacity:int=90,headway:int=30) -> object:
    """
    Returns the node_pairs to only have stations which are also present in the JSON file.
    Adds the cancelled services & disruption data to the service df.

    """
    print("Constructing service edgelist")
    # Get only stops that occur in the json files to be in the service edgelist (needs only one per edge) 
    node_pairs = node_pairs.copy()
    node_pairs = node_pairs[node_pairs["from_stop"].isin(track_nodes.index) | node_pairs["to_stop"].isin(track_nodes.index)]

    node_pairs['travel_time'] = node_pairs.groupby(node_pairs.index)['travel_time'].transform('mean') # set avg. tt inplace 

    disrupted_services = (
        disrupted_services.groupby(disrupted_services.index)
        .agg({
            'total_services'     : 'sum',
            'cancelled_services' : 'sum',
        }))

    # Percentage of services that were cancelled compared to all services operated (from RDT data)
    disrupted_services['pct_services_cancelled'] = round((disrupted_services['cancelled_services'] / disrupted_services['total_services']) * 100,1)

    node_pairs = node_pairs.merge(
        disrupted_services,
        how='left',
        left_index=True,
        right_index=True,
    )

    # Remove service edge that does not exist
    node_pairs = node_pairs[
        ~(node_pairs.index == ("Diemen Zuid","Hilversum"))
    ]

    ipv_data = (
        ipv_services[['p85_max_travel_time_minutes','total_services','avg_headway_minutes','service_type_breakdown']] 
        .groupby(ipv_services.index)
        .agg({
            'p85_max_travel_time_minutes': "mean",
            'total_services'             : "sum",
            'avg_headway_minutes'        : "min",
            'service_type_breakdown'     : agg_dicts,
        })
    )

    node_pairs = node_pairs.merge(
        ipv_data,
        how='left',
        left_index=True,
        right_index=True,
    )

    node_pairs['avg_headway_minutes'] = node_pairs['avg_headway_minutes'].fillna(headway) 
    node_pairs['capacity'] = round((120 / node_pairs['avg_headway_minutes']) * ipv_capacity * 2,0)

    # Rename and reorder
    node_pairs = node_pairs[['from_stop','to_stop',"travel_time", "capacity","total_services_x", "cancelled_services", "pct_services_cancelled","p85_max_travel_time_minutes","total_services_y","service_type_breakdown"]].rename(columns={
        "total_services_x"            : 'total_services',
        "p85_max_travel_time_minutes" : "ipv_travel_time",
        "total_services_y"            : "total_ipv_services",
        "service_type_breakdown"      : "ipv_service_types",
    })

    #### Connect disruption data with edges ####
    # Strip station names from the RDT list
    disruption_durations["station_list"] = (
        disruption_durations["rdt_station_names"]
        .fillna("")
        .str.split(",")
        .apply(lambda x: [s.strip() for s in x if s.strip()])
    )
    station_sets = disruption_durations.set_index("rdt_id")["station_list"].apply(set).to_dict() # Set containing every observed list of disrupted stations

    # Explode to one row per (disruption, station)
    dis_exploded = (
        disruption_durations
        .drop(columns=["station_list"])
        .assign(station=disruption_durations["station_list"].values)
        .explode("station")
    )
    dis_exploded["station"] = dis_exploded["station"].str.strip()

    # Left-join on from_stop, then filter to_stop
    step1 = node_pairs.merge(
        dis_exploded,
        left_on="from_stop",
        right_on='station',
        how="left"
    )

    mask_unmatched = step1["rdt_id"].isna()
    # Cross-check both endpoints against station_sets
    mask_both_match = step1.apply(
        lambda r: pd.notna(r["rdt_id"])
                and r["from_stop"] in station_sets.get(r["rdt_id"], set())
                and r["to_stop"]   in station_sets.get(r["rdt_id"], set()),
        axis=1,
    )
    result = step1[mask_unmatched | mask_both_match].reset_index(drop=True)

    # Aggregate causes & ids ordered by duration desc
    def _agg_edge(group):
        group = group.drop(columns=["from_stop", "to_stop"], errors="ignore")
        matched = group.dropna(subset=["rdt_id"]).sort_values("duration_minutes", ascending=False)

        affected = [
            sorted(station_sets.get(did, set()))
            for did in matched["rdt_id"]
        ]

        all_stations = [station for sub_list in affected for station in sub_list]
        co_disruption_count = dict(Counter(all_stations))

        return pd.Series({
            "n_disruptions":     len(matched),
            "total_duration":    round(matched["duration_minutes"].sum()),
            "avg_duration":      round(matched["duration_minutes"].mean()) if len(matched) > 0 else 0,
            "max_duration":      round(matched["duration_minutes"].max()),
            "causes":            matched["cause_en"].tolist(),
            "disruption_ids":    matched["rdt_id"].astype(int).tolist(),
            "durations":         matched["duration_minutes"].tolist(),
            "affected_stations": affected,
            "co_disruption_count": co_disruption_count,
            "total_stations_codisrupted": sum(co_disruption_count.values()),
        })

    # Count the times a disruption occured with both edge neighboors 
    edges_with_disruptions = (
        result
        .groupby(["from_stop", "to_stop"], dropna=False)
        .apply(_agg_edge)
        .reset_index()
    )

    # Fill edges that matched nothing with tidy empty defaults
    edges_with_disruptions["n_disruptions"]  = edges_with_disruptions["n_disruptions"].fillna(0).astype(int)
    edges_with_disruptions["total_duration"] = edges_with_disruptions["total_duration"].fillna(0.0)
    edges_with_disruptions["avg_duration"]   = edges_with_disruptions["avg_duration"].fillna(0.0)
    edges_with_disruptions["max_duration"]   = edges_with_disruptions["max_duration"].fillna(0.0)

    # aggregate the different values
    COLLECTION_COLS: dict[str, type] = {
        "causes"                : list,
        "disruption_ids"        : list,
        "durations"             : list,
        "affected_stations"     : list,
        "co_disruption_count"   : dict,
    }

    def _coerce_collection(series: pd.Series, expected_type: type) -> pd.Series:
        default = [] if expected_type is list else {}
        return series.apply(lambda x: x if isinstance(x, expected_type) else default)

    for col, expected_type in COLLECTION_COLS.items():
        edges_with_disruptions[col] = _coerce_collection(edges_with_disruptions[col], expected_type)

    edges_with_disruptions = make_edge_key(edges_with_disruptions, src='from_stop',dst='to_stop')
    edges_with_disruptions.drop(columns=['from_stop','to_stop'], inplace=True)

    node_pairs = node_pairs.merge(
        edges_with_disruptions[['n_disruptions','avg_duration','total_duration','max_duration','co_disruption_count','total_stations_codisrupted','affected_stations']],
        how='inner',
        left_index=True,
        right_index=True,
    )

    node_pairs['codisrupted_passengers'] = sf.compute_disrupted_passengers(node_pairs,track_nodes)

    node_pairs = node_pairs[~node_pairs.index.duplicated(keep='first')]

    #### OV joining ####
    ov_data = ov_services[['travel_time_ov_min','avg_peak_headway_min']].groupby(ov_services.index).agg({'travel_time_ov_min' : "max",'avg_peak_headway_min': "min"})

    # Where a service existed but no headway was found in the data (eg. >2hr headway) use passed constant
    ov_data['avg_peak_headway_min'] = ov_data['avg_peak_headway_min'].fillna(headway)
    ov_data[['ov_capacity']] = round((120 / ov_data[['avg_peak_headway_min']]) * ov_capacity * 2,0)

    node_pairs = node_pairs.merge(
        ov_data,
        how='left',
        left_index=True,
        right_index=True,
    )

    return node_pairs

def coord_positions(table: object, elements: str) -> dict:
    """
    Extracts the coordinates of the 'tracks' or 'stations' table and
    makes them into a pos dict that can be passed to plotting.
    
    Has to use the track edgelist instead of the track nodes since not all nodes had lat-long given. 
    """

    # Track nodes
    if elements == "segments_df":
        pos_from = dict(
            zip(
                table['Name_from'],
                zip(table["from_lng"], table["from_lat"])
            )
        )

        pos_to = dict(
            zip(
                table["Name_to"],
                zip(table["to_lng"], table["to_lat"])
            )
        )

        result =  pos_to | pos_from # joined because not all in the _to are also in the _from

        table.drop(['from_lat','from_lng','to_lat','to_lng'], inplace=True, axis=1)

    # Station nodes
    elif elements == "stations":
        result = dict(
            zip(
                table["name_long"],
                zip(table["geo_lng"], table["geo_lat"])
            )
        )

    return result

def create_ipv_graph(services_ipv: pd.DataFrame, track_nodes:pd.DataFrame) -> nx.Graph:
    # The keyed directed graph is passed with all sorts of edges
    # The values are aggregated to undirected edges
    # These are filtered to only include stations also present in the study area

    # Remove all rows where total_services = cancelled_services
    services_ipv = services_ipv[services_ipv['total_services'] != services_ipv['cancelled_services']]

    # Aggregated across undirected pk
    ipv_data = (
        services_ipv[['p85_max_travel_time_minutes','total_services','capacity','service_type_breakdown','departure_station','arrival_station']] 
        .groupby(services_ipv.index)
        .agg({
            'p85_max_travel_time_minutes': "mean",
            'total_services'             : "sum",
            'capacity'                   : "sum",
            'service_type_breakdown'     : agg_dicts,
            'departure_station'          : 'first',
            'arrival_station'            : 'first',
        })
    ).rename(columns={'p85_max_travel_time_minutes' : 'ipv_travel_time'})

    mask = (
        ipv_data['departure_station'].isin(track_nodes.index)
        & ipv_data['arrival_station'].isin(track_nodes.index)
    )

    ipv_filtered = ipv_data[mask]

    # Create speed for fitting
    ipv_filtered = ipv_filtered.merge(
        track_nodes[['Lat','Lng']],
        how='left',
        left_on=['departure_station'],
        right_index=True,
        suffixes=['_from','_to']
    )

    ipv_filtered = ipv_filtered.merge(
        track_nodes[['Lat','Lng']],
        how='left',
        left_on=['arrival_station'],
        right_index=True,
        suffixes=['_to','_from']
    )

    ipv_filtered["geo_length"] = ipv_filtered.apply(
        lambda row: geodesic(
            (row["Lat_from"], row["Lng_from"]),
            (row["Lat_to"], row["Lng_to"])
        ).km,
        axis=1
    )

    ipv_filtered['speed'] = ipv_filtered["geo_length"] / ipv_filtered["ipv_travel_time"] #km/min

    G_ipv = nx.from_pandas_edgelist(ipv_filtered, 'departure_station','arrival_station',True)

    return G_ipv

def attach_track_nodes_to_service_edges(G_services:nx.Graph,G_tracks:nx.Graph) -> nx.Graph:
    """
    Loops over all edges in service graph and 
    attaches the track elements said edge passes over.
    """
    for u, v, data in G_services.edges(data=True):
        try:
            path = nx.shortest_path(G_tracks, source=u, target=v)
            data['track_nodes'] = path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            data['track_nodes'] = []  # Edge has no track paths (eg gens or bad bentheim trackage)

    return G_services 

def create_blocks(G_tracks: nx.Graph, num_matching_nodes_required: int = 2):
    """
    Finds all shortest paths that exist between all possible block stations.
    Creates a block id for every unique block, adds it to the graph
    """
    block_nodes = {node for node, val in nx.get_node_attributes(G_tracks, 'ic_station').items() if val}
    block_segments = {}

    def _find_adjacent_block_nodes(start: str) -> list[str]:
        """Returns list of block nodes accessible from this node"""
        found = []
        stack = [(neighbor, {start, neighbor}) for neighbor in G_tracks.neighbors(start)]
        while stack:
            node, visited = stack.pop()
            if node in block_nodes:
                found.append(node)
            else:
                for neighbor in G_tracks.neighbors(node):
                    if neighbor not in visited:
                        stack.append((neighbor, visited | {neighbor}))
        return found

    # Collect all paths
    for block_node in block_nodes:
        for end_block in _find_adjacent_block_nodes(block_node):
            key = tuple(sorted([block_node, end_block]))
            if key in block_segments:
                continue
            allowed_nodes = (set(G_tracks.nodes()) - block_nodes) | {block_node, end_block}
            G_sub = G_tracks.subgraph(allowed_nodes)
            try:
                path = nx.shortest_path(G_sub, source=block_node, target=end_block, weight='travel_time')
            except nx.NetworkXNoPath:
                continue
            block_segments[key] = {
                "block_start":        path[0],
                "block_end":          path[-1],
                "full_path":          path,
                "intermediate_nodes": set(path[1:-1]),  # set for O(1) lookup
            }

    # Which segments share intermediate nodes
    node_to_keys = {}
    for key, seg in block_segments.items():
        for node in seg["intermediate_nodes"]:
            node_to_keys.setdefault(node, []).append(key)

    seg_graph = nx.Graph()
    seg_graph.add_nodes_from(block_segments.keys())

    pair_counts = defaultdict(int)
    for node, keys in node_to_keys.items():
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                pair_counts[keys[i], keys[j]] += 1

    for (k1, k2), count in pair_counts.items():
        if count >= num_matching_nodes_required:
            seg_graph.add_edge(k1, k2)

    n_blocks = nx.number_connected_components(seg_graph)
    print(f"Blocks (connected components): {n_blocks}")

    # Assign block_id per connected component and tag graph elements
    for block_id, component in enumerate(nx.connected_components(seg_graph)):
        for key in component:
            seg = block_segments[key]
            path = seg["full_path"]
            # Tag intermediate nodes only (not IC stations)
            for node in seg["intermediate_nodes"]:
                G_tracks.nodes[node]['block_id'] = block_id
            # Tag edges
            for u, v in zip(path, path[1:]):
                if G_tracks.is_multigraph():
                    for edge_key in G_tracks[u][v]:
                        G_tracks[u][v][edge_key]['block_id'] = block_id
                else:
                    G_tracks[u][v]['block_id'] = block_id

    return G_tracks, n_blocks

def create_ov_graph(services_ov: pd.DataFrame, track_nodes:pd.DataFrame) -> nx.Graph:
    """
    Graph of the OV services.
    """
    ov_data = (services_ov[[
            'source_station_name',
            'target_station_name',
            'agency_id',
            'route_short_name',
            'route_long_name',
            'travel_time_ov_min',
            'route_id']]
        .groupby(services_ov.index)
        .agg({
            'source_station_name':'first',
            'target_station_name':'first',
            'agency_id': 'first',
            'route_short_name':'first',
            'route_long_name':'first',
            'travel_time_ov_min':'mean',
            'route_id' : 'first',
        })
    )

    mask = (
        ov_data['source_station_name'].isin(track_nodes.index)
        & ov_data['target_station_name'].isin(track_nodes.index)    
    )

    ov_filtered = ov_data[mask]

    G_ov = nx.from_pandas_edgelist(ov_filtered, "source_station_name","target_station_name",True)
    G_ov = sf.set_node_attributes_from_dataframe(G_ov, track_nodes)

    return G_ov
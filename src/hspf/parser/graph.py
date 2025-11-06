# -*- coding: utf-8 -*-
"""
Created on Thu Feb  6 14:50:45 2025

@author: mfratki
"""
import networkx as nx
import pandas as pd
import numpy as np
import math

class Node(object):
    nodes = []

    def __init__(self, label):
        self._label = label

    def __str__(self):
        return self._label
   
    
def create_graph(uci):
    
    
    # Define Node labels
    opn_sequence = uci.table('OPN SEQUENCE').reset_index(drop=True)
    opn_sequence.set_index(['OPERATION','SEGMENT'],inplace=True)
    opn_sequence_labels = opn_sequence.index.drop_duplicates().to_list()
    G = nx.MultiDiGraph()
    [G.add_node(node, id = node, category = 'OPERATION', type_id = label[1], type = label[0] ) for node,label in enumerate(opn_sequence_labels)] 

    # ext_sources = uci.table('EXT SOURCES').reset_index(drop=True)
    # ext_sources.set_index(['SVOL','SVOLNO'],inplace=True)
    # ext_sources_labels = ext_sources.index.drop_duplicates().to_list()
    # [G.add_node(max(G.nodes) + 1,id = max(G.nodes) + 1, type = label[0], type_id = label[1], category = 'WDM') for node,label in enumerate(ext_sources_labels)] 
            
    labels = {v: i for i, v in enumerate(opn_sequence_labels)}# + ext_sources_labels)}
    
    #Define edges from Schematic Block
    schematic = uci.table('SCHEMATIC').reset_index(drop=True).set_index(['SVOL','SVOLNO'])
    schematic['snode'] = schematic.index.map(labels)
    schematic.reset_index(inplace=True)
    schematic = schematic.set_index(['TVOL','TVOLNO'])
    schematic['tnode'] = schematic.index.map(labels)
    schematic.reset_index(inplace=True)
    # Nodes in the schematic block that are missing from the opn sequence block (usually the outlet reach)
    #schematic.loc[schematic.index.map(labels).isna()]
    schematic = schematic.loc[schematic[['snode','tnode']].dropna().index] # For now remove that missing node
    schematic.loc[:,'TMEMSB1'].replace('',pd.NA,inplace=True)
    schematic.loc[:,'TMEMSB2'].replace('',pd.NA,inplace=True)
    schematic.loc[:,'MLNO'].replace('',pd.NA,inplace=True)

    schematic = schematic.astype({'snode': int,'tnode':int,'MLNO':pd.Int64Dtype(),'TMEMSB1':pd.Int64Dtype(),'TMEMSB2':pd.Int64Dtype()})
    for index, row in schematic.iterrows():
        if row['SVOL'] == 'GENER':
            G.add_edge(row['snode'],row['tnode'],
                             mlno = row['MLNO'],
                             count = row['AFACTR'],
                             tmemsb1 = row['TMEMSB1'],
                             tmemsb2 = row['TMEMSB2'])
        else:
            G.add_edge(row['snode'],row['tnode'],
                             mlno = row['MLNO'],
                             area = row['AFACTR'],
                             tmemsb1 = row['TMEMSB1'],
                             tmemsb2 = row['TMEMSB2'])
        
 

    # Add property information
    geninfo = uci.table('PERLND','GEN-INFO')
    for index,row in geninfo.iterrows():
        G.nodes[labels[('PERLND',index)]]['name'] = row['LSID']

        
    geninfo = uci.table('IMPLND','GEN-INFO')
    for index,row in geninfo.iterrows():
        G.nodes[labels[('IMPLND',index)]]['name'] = row['LSID']
        
    geninfo = uci.table('RCHRES','GEN-INFO')
    for index,row in geninfo.iterrows():
        G.nodes[labels[('RCHRES',index)]]['name'] = row['RCHID']
        G.nodes[labels[('RCHRES',index)]]['lkfg'] = row['LKFG']

    G.labels = labels
    return G


def _add_subgraph_labels(G,G_sub):
    G_sub.labels = {label:node for label, node in G.labels.items() if node in G_sub.nodes}
    return G_sub

def subgraph(G,nodes):
    def add_subgraph_labels(G,G_sub):
        G_sub.labels = {label:node for label, node in G.labels.items() if node in G_sub.nodes}
        return G_sub
    return add_subgraph_labels(G,G.subgraph(nodes).copy())

def _predecessors(G,node_id:int):
    return [G.nodes[node] for node in G.predecessors(node_id)]
    
def _successors(G, node_id:int):
    return [G.nodes[node] for node in G.successors(node_id)]

def _ancestors(G,node_id:int):
    '''
    Returns a list of nodes reachable from node node_id
    '''
    #set(nx.get_node_attributes(G,'type').values()) # Get all node types
    return [G.nodes[node] for node in list(nx.ancestors(G,node_id))]

def _descendants(G,node_id:int):
    '''
    Returns a list of nodes reachable from node node_id
    '''
    return [G.nodes[node] for node in list(nx.descendants(G,node_id))]


def predecessors(G,node_type:str,node_id:int):
    '''
    Returns a list of nodes of a give type with a direct connection to node_id
    '''
    return [G.nodes[node] for node in list(G.predecessors(node_id)) if G.nodes[node]['type'] == node_type]

def successors(G,node_type:str,node_id:int):
    '''
    Returns a list of nodes of a given type that node_id has a direct connection to
    '''
    return [G.nodes[node] for node in list(G.successors(node_id)) if G.nodes[node]['type'] == node_type]
      
def ancestors(G,node_id:int,ancestor_node_type:str):
    '''
    Returns a list of nodes of a give type reachable from node node_id
    '''
    #set(nx.get_node_attributes(G,'type').values()) # Get all node types
    return [G.nodes[node] for node in list(nx.ancestors(G,node_id)) if G.nodes[node]['type'] == ancestor_node_type]

def descendants(G,node_id:int,descendant_node_type:str):
    '''
    Returns a list of nodes of a give type reachable from node node_id
    '''
    return [G.nodes[node] for node in list(nx.descendants(G,node_id)) if G.nodes[node]['type'] == descendant_node_type]


def node_types(G):
    return set(nx.get_node_attributes(G,'type').values())

def node_categories(G):
    return set(nx.get_node_attributes(G,'category').values())

def node_labels(G):
    return {(node['type'],node['type_id']): node['id']  for _, node in G.nodes(data=True)}

def get_node_id(G,node_type,node_type_id):
    return node_labels(G)[(node_type,node_type_id)]

def get_nodes(G,node_type):
    return [data for node_id, data in G.nodes(data=True) if data['type'] == node_type]

def get_node_ids(G,node_type):
    return [node_id for node_id, data in G.nodes(data=True) if data['type'] == node_type]


def nodes(G,node_type,node_type_id,adjacent_node_type):
    return (node for node in predecessors(G,node_type,G.labels[(node_type,node_type_id)]) if G.nodes[node]['type'] == adjacent_node_type)




#%% Methods using node_type, node_type_id interface

def upstream_network(G,reach_id):
    node_id = get_node_id(G,'RCHRES',reach_id)
    return G.subgraph([node_id] + list(nx.ancestors(G,node_id))).copy()

def downstream_network(G,reach_id):
    node_id = get_node_id(G,'RCHRES',reach_id)
    return G.subgraph([node_id] + list(nx.descendants(G,node_id))).copy()

def subset_network(G,reach_id,upstream_reach_ids = None):
    G = upstream_network(G,reach_id)
    if upstream_reach_ids is not None:
        for upstream_reach_id in upstream_reach_ids:
            G.remove_nodes_from(get_node_ids(upstream_network(G,upstream_reach_id),'RCHRES'))
        #assert([len(sinks(G)) == 0,sinks(G)[0] == reach_id])
    return G

def upstream_nodes(G,reach_id,upstream_node_type):
    return ancestors(G,get_node_id(G,'RCHRES',reach_id),upstream_node_type)

def downstream_nodes(G,reach_id,downstream_node_type):
    return descendants(G,get_node_id(G,'RCHRES',reach_id),downstream_node_type)

def adjacent_nodes(G,reach_id):
    node_id = get_node_id(G,'RCHRES',reach_id)
    return _predecessors(G,node_id) + _successors(G,node_id)

def adjacent_upstream_nodes(G,reach_id,upstream_node_type):
    return predecessors(G,upstream_node_type,get_node_id(G,'RCHRES',reach_id))

    
def adjacent_downstream_nodes(G,reach_id,downstream_node_type):
    return successors(G,downstream_node_type,get_node_id(G,'RCHRES',reach_id))


def reach_node(G,reach_id):
    return  get_node_id(G,'RCHRES',reach_id)

def get_perlnd_node(G,perlnd_id):
    return  get_node_id(G,'PERLND',perlnd_id)

def get_implnd_node(G,implnd_id):
    return  get_node_id(G,'IMPLND',implnd_id)






#%%# Public interfaces

def get_node_type_ids(G,node_type = 'RCHRES'):
    return [data['type_id'] for node, data in G.nodes(data = True) if data['type'] == node_type]

def get_reaches(G):
    return get_node_type_ids(G, node_type = 'RCHRES')
    
def outlets(G):
    return [G.nodes[node]['type_id'] for node, out_degree in G.out_degree(get_node_ids(G,'RCHRES')) if out_degree == 0]

def adjacent_operations(G,operation,reach_id):
    assert operation in ['RCHRES','PERLND','IMPLND']
    return [G.nodes[perlnd_node_id]['id'] for perlnd_node_id in predecessors(G,operation,G.labels[('RCHRES',reach_id)])]

def adjacent_perlnds(G,reach_id):
    return [G.nodes[perlnd_node_id] for perlnd_node_id in predecessors(G,'PERLND',G.labels[('RCHRES',reach_id)])]

def adjacent_implnds(G,reach_id):
    return [G.nodes[perlnd_node_id] for perlnd_node_id in predecessors(G,'IMPLND',G.labels[('RCHRES',reach_id)])]

def adjacent_reaches(G,reach_id):
    return [G.nodes[perlnd_node_id] for perlnd_node_id in predecessors(G,'RCHRES',G.labels[('RCHRES',reach_id)])]

def upstream_adjacent_reachs(G,reach_id):
    return [G.nodes[reach_id]['id'] for reach_id in predecessors(G,'RCHRES',G.labels[('RCHRES',reach_id)])]
    
def downstream_adjacent_reachs(G,reach_id):
    return successors(G,'RCHRES',G.labels[('RCHRES',reach_id)])

def upstream_reachs(G,reach_id,upstream_reach_ids = None):
    return [node['type_id'] for node in ancestors(G,get_node_id(G,'RCHRES',reach_id),'RCHRES')]
    
def downstream_reachs(G,reach_id, upstream_reach_ids = None):
    return [node['type_id'] for node in descendants(G,get_node_id(G,'RCHRES',reach_id),'RCHRES')]

def routing_reachs(G):
    return [reach_id for reach_id in get_reaches(G) if is_routing(G,reach_id)]
    
def is_routing(G,reach_id):
    return all([node['type'] not in ['PERLND', 'IMPLND'] for node in adjacent_nodes(G,reach_id)])

def watershed_area(G,reach_ids):
    return float(np.nansum(list(nx.get_edge_attributes(make_watershed(G,reach_ids),'area').values())))

def catchment_area(G,reach_id):
    return float(np.nansum(list(nx.get_edge_attributes(make_catchment(G,reach_id),'area').values())))


def paths(G,reach_id,source_type = 'RCHRES'):
    reach_node = get_node_id(G,'RCHRES',reach_id)
    inv_labels = {v: k[1] for k, v in node_labels(G).items()}
    return {inv_labels[source['id']]:[inv_labels[node] for node in nx.shortest_path(G,source['id'],reach_node)] for source in ancestors(G,reach_node,source_type)}

def count_ancestors(G,node_type,ancestor_node_type):
    return {node['type_id']:len(ancestors(G,node['id'],ancestor_node_type)) for node in get_nodes(G,node_type)}

# def catchment_ids(G):
#     result = []
#     for node in get_node_ids(G,'RCHRES'):
#         upstream_nodes = G.predecessors(node)
#         if any([G.nodes[up]['type'] in ['PERLND','IMPLND'] for up in upstream_nodes]):
#             result.append(G.nodes[node]['type_id'])
#     return result

# Very expensive. Should probably standardize it so routing reaches have no implnds/perlnds
def catchment_ids(G):
    result = []
    for node in get_node_ids(G,'RCHRES'):
        upstream_nodes = G.predecessors(node)
        if any([G.nodes[up]['type'] in ['PERLND','IMPLND'] for up in upstream_nodes]):
            cat = make_catchment(G,G.nodes[node]['type_id'])
            if area(cat) > 0:
                result.append(G.nodes[node]['type_id'])
    return result

# Catchment constructor
def make_catchment(G,reach_id):
    node_id = get_node_id(G,'RCHRES',reach_id)
    catchment = G.edge_subgraph(G.in_edges(node_id,keys=True))
    nx.set_node_attributes(catchment,node_id,'catchment_id')
    return catchment

from itertools import chain

def make_watershed(G,reach_ids):
    '''
    Creates a sugraph representing the the catchments upstream of the specified hspf model reaches. Note that a negative reach_ids indicate to subtract that area from the total.
    
    
    ''' 
    node_ids = set([get_node_id(G,'RCHRES',reach_id) for reach_id in reach_ids if reach_id > 0])
    nodes_to_exclude = set([get_node_id(G,'RCHRES',abs(reach_id)) for reach_id in reach_ids if reach_id < 0])
    node_ids = node_ids - nodes_to_exclude
    
    
    nodes = [list(nx.ancestors(G,node_id)) for node_id in node_ids]
    nodes.append(node_ids)
    nodes = list(set(chain.from_iterable(nodes)))
    watershed = subgraph(G, nodes)
    catchment_id = '_'.join([str(reach_id) for reach_id in reach_ids])
    nx.set_node_attributes(watershed,node_ids,catchment_id)
    return watershed


# def catcments(G):
#     cats = [Catchment(graph.make_catchment(G,reach_id) for reach_id in graph.get_node_type_ids(G,'RCHRES'))]

#     return 
        
#         for u, v, edge_data in graph.make_catchment(G,reach_id).edges(data=True):
#             source_node_attributes = G.nodes[u]
#             # Add or update edge attributes with source node attributes
#             edge_data["source_type"] = source_node_attributes.get("type")
#             edge_data["source_name"] = source_node_attributes.get("name")
#             edge_data["source_type_id"] = source_node_attributes.get("type_id")
#             cats.append(edge_data)
        
#     return pd.DataFrame(cats)
                     
                     
#                      for node in G.nodes:
#         upstream_nodes = G.predecessors(node)
#         if any(G.nodes[up]['type'] in ['PELND','IMPLND'] for up in upstream_nodes):
#             result.append(node)

#     return None
# Catchment selectors

'''
Properties of an HSPF catchment
 - area
 - outlet
 - inlets
 - inflows
 - outflows
 - reach
 
 
 
'''

        
# def area_by_landcover(G):
#     for k, v in nx.get_edge_attributes(catchment,'aread').items
#     np.nansum([v for k, v in nx.get_edge_attributes(catchment,'area').items()])
# combined_data = []
# for u, v, edge_data in test.edges(data=True):
#     row = {
#         'source': u,
#         'target': v,
#         **test.nodes[u],
#         **test.nodes[v],
#         **edge_data
#     }
#     combined_data.append(row)
    
def area_by_landcover(catchment):
    return np.nansum([v for k, v in nx.get_edge_attributes(catchment,'area').items()])


def area(catchment):
    return np.nansum([v for k, v in nx.get_edge_attributes(catchment,'area').items()])

def operation_ids(catchment,operation):
    return [k[1] for k,v in catchment.labels.items() if k[0] == operation]

def dsn(catchment,tmemn):
    return [catchment.nodes[k[0]]['id']  for k,v in nx.get_edge_attributes(catchment,'tmemn').items() if v == tmemn]
    
# catchment is a subset of a networkx graph constructed from a UCI file.
class Catchment():
    def __init__(self,catchment):
        self.catchment = catchment
    
    def area(self):
        return np.nansum([v for k, v in nx.get_edge_attributes(self.catchment,'area').items()])
    
    def operation_ids(self,operation):
        return [self.catchment.nodes[node]['type_id'] for node in get_node_ids(self.catchment,operation) if node in self.catchment.nodes]
    
    def dsn(self,tmemn):
        return [self.catchment.nodes[k[0]]['id']  for k,v in nx.get_edge_attributes(self.catchment,'tmemn').items() if v == tmemn]
    
    def to_dataframe():
        return 
# def _watershed(G,reach_id):
    
#     predecessors = (list(G.predecessors(node)))
#     node = G.labels[('RCHRES',reach_id)]
#     subgraph = nx.subgraph(G,nx.ancestors(G,node))
#     return subgraph


# def _catchment(G,reach_id):
    
#     node = G.labels[('RCHRES',reach_id)]
    
#     subgraph = nx.subgraph(G,nx.ancestors(G,node))
#     return subgraph


# def paths(G,reach_id):
    
#     {source:[node for node in nx.shortest_path(G,source,reach_id)] for source in nx.ancestors(G,reach_id)}




#%% Legacy Methods for Backwards compatability
class reachNetwork():
    def __init__(self,uci,reach_id = None):
        self.uci = uci
        self.G = create_graph(uci)
        self.catchment_ids = catchment_ids(self.G)
        self.routing_reaches = self._routing_reaches()
        self.lakes = self._lakes()
        self.schematic = uci.table('SCHEMATIC').astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR':float})
    
    def get_node_type_ids(self,node_type):
        return get_node_type_ids(self.G, node_type)
    
    def _upstream(self,reach_id,node_type = 'RCHRES'):
        '''
        Returns list of model reaches upstream of inclusive of reach_id

        '''
        upstream = [node['type_id'] for node in upstream_nodes(self.G,reach_id,node_type) if node['type'] == 'RCHRES']
        upstream.append(reach_id)
        return upstream

    def _downstream(self,reach_id,node_type = 'RCHRES'):
        '''
        Returns list of model reaches downstream inclusive of reach_id

        '''
        downstream = [node['type_id'] for node in downstream_nodes(self.G,reach_id,node_type) if node['type'] == 'RCHRES']
        downstream.insert(0,reach_id)
        return downstream
        
    def calibration_order(self,reach_id,upstream_reach_ids = None):
        return calibration_order(self.G,reach_id,upstream_reach_ids)
    
    def station_order(self,reach_ids):
        raise NotImplementedError()
        
    
    def downstream(self,reach_id):
        '''
        Downstream adjacent reaches

        '''
        return [node['type_id'] for node in successors(self.G,'RCHRES',get_node_id(self.G,'RCHRES',reach_id))]
    
    def upstream(self,reach_id):
        '''
        Upstream adjacent reaches

        '''
        return  [node['type_id'] for node in predecessors(self.G,'RCHRES',get_node_id(self.G,'RCHRES',reach_id))]
        
    def get_opnids(self,operation,reach_id, upstream_reach_ids = None):
        '''
        Operation IDs with a path to reach_id. Operations upstream of upstream_reach_ids will not be included

        '''
        return get_opnids(self.G,operation=operation,reach_id = reach_id, upstream_reach_ids = upstream_reach_ids)
    
    def operation_area(self,operation,opnids = None):
        return operation_area(self.uci,operation)  
        
    def drainage(self,reach_id):
        # Merge source node attributes into edge attributes
    
        edges = []
        for u, v, edge_data in make_catchment(self.G,reach_id).edges(data=True):
            source_node_attributes = self.G.nodes[u]
            # Add or update edge attributes with source node attributes
            edge_data["source_type"] = source_node_attributes.get("type")
            edge_data["source_name"] = source_node_attributes.get("name")
            edge_data["source_type_id"] = source_node_attributes.get("type_id")
            edges.append(edge_data)
        
        return pd.DataFrame(edges)
    
    def subwatersheds(self,reach_ids = None):
        df = subwatersheds(self.uci)
        if reach_ids is None:
            reach_ids = get_node_type_ids(self.G,'RCHRES')
        return df.loc[df.index.intersection(reach_ids)]
    
    def subwatershed(self,reach_id):
        return subwatershed(self.uci,reach_id) #.loc[reach_id]
    
    def subwatershed_area(self,reach_id):
        area = self.drainage(reach_id).query("source_type in ['PERLND','IMPLND']")['area'].sum()
        # if (reach_id in self.lakes()) & (f'FTABLE{reach_id}' in self.uci.table_names('FTABLES')):
        #     area = area + self.lake_area(reach_id)
        return area
    
    def reach_contributions(self,operation,opnids):
        return reach_contributions(self.uci,operation,opnids)
    
    def drainage_area(self,reach_ids):
        return watershed_area(self.G,reach_ids)
    
    def drainage_area_landcover(self,reach_id,group = True):
        reach_ids = self._upstream(reach_id)
        areas = pd.concat([self.subwatershed(reach_id) for reach_id in reach_ids]).groupby(['SVOL','SVOLNO'])['AFACTR'].sum()
        
        if group:    
            areas = pd.concat([areas[operation].groupby(self.uci.opnid_dict[operation].loc[areas[operation].index,'LSID'].values).sum() for operation in ['PERLND','IMPLND']])
        return areas

    def outlets(self):
        return [self.G.nodes[node]['type_id'] for node, out_degree in self.G.out_degree() if (out_degree == 0) & (self.G.nodes[node]['type'] == 'RCHRES')]

    def _lakes(self):
        return list(self.uci.table('RCHRES','GEN-INFO').query('LKFG == 1',engine = 'python').index.astype(int))        
    
    def lake_area(self,reach_id):
        return self.uci.table('FTABLES',f'FTABLE{reach_id}')['Area'].max()
    
    def _routing_reaches(self):
        return [reach_id for reach_id in self.get_node_type_ids('RCHRES') if reach_id not in self.catchment_ids]

    def paths(self,reach_id):
        return paths(self.G,reach_id)
    
    
def calibration_order(G,reach_id,upstream_reach_ids = None):
    '''
    Determines the order in which the specified reaches should be calibrated to
    prevent upstream influences. Primarily helpful when calibrating sediment and
    adjusting in channel erosion rates.
    '''
    
    order = []
    Gsub = subgraph(G,get_node_ids(G,'RCHRES'))
    while(len(Gsub.nodes)) > 0:
   
        nodes_to_remove = [node for node, in_degree in Gsub.in_degree() if in_degree == 0]
        order.append([G.nodes[node]['type_id'] for node in nodes_to_remove])
        Gsub.remove_nodes_from(nodes_to_remove)         
    return order
    



def get_opnids(G,operation,reach_id = None, upstream_reach_ids = None):
    G = subset_network(G,reach_id,upstream_reach_ids)
    return ancestors(G,get_node_id(G,'RCHRES',reach_id),operation)
    perlnds = [node['type_id'] for node in get_nodes(G,'PERLND')]
    implnds = [node['type_id'] for node in get_nodes(G,'IMPLND')]
    reachs = [node['type_id'] for node in get_nodes(G,'RCHRES')]
    return {'RCHRES':reachs,'PERLND':perlnds,'IMPLND':implnds}[operation]
    #return reachs,perlnds,implnds

def drainage(uci,reach_ids):
    return subwatersheds(uci).loc[reach_ids].reset_index()[['SVOL','LSID','AFACTR']].groupby(['LSID','SVOL']).sum()



def drainage_area(uci,reach_ids,drng_area = 0):
    if len(reach_ids) == 0:
        return drng_area
    else:
        sign = math.copysign(1,reach_ids[0])
        reach_id = int(reach_ids[0]*sign)
        drng_area = drng_area + sign*uci.network.drainage_area(reach_id)
        drainage_area(uci,reach_ids[1:],drng_area)
                

def reach_contributions(uci,operation,opnids):
    schematic = uci.table('SCHEMATIC').set_index('SVOL')
    schematic = schematic[schematic.index == operation]
    schematic = schematic[schematic['TVOL'] == 'RCHRES'][['SVOLNO','TVOLNO','AFACTR']].astype({'SVOLNO':int,'TVOLNO':int,'AFACTR':float})
    schematic = pd.concat([schematic[['SVOLNO','TVOLNO','AFACTR']][schematic['SVOLNO'] == opnid] for opnid in opnids])
    schematic = schematic.reset_index()
    schematic = schematic.groupby(['SVOL','SVOLNO','TVOLNO']).sum()
    #schematic.columns = [operation,'reach','reachshed']
    #schematic.set_index(operation,drop = True,inplace = True)
    return schematic

def subwatersheds(uci):
    schematic = uci.table('SCHEMATIC').set_index('SVOL')
    schematic = schematic[(schematic.index == 'PERLND') | (schematic.index == 'IMPLND')]
    schematic = schematic[schematic['TVOL'] == 'RCHRES'][['SVOLNO','TVOLNO','AFACTR','MLNO']].astype({'SVOLNO':int,'TVOLNO':int,'AFACTR':float,'MLNO':int})
    schematic.reset_index(inplace=True,drop=False)
    schematic.set_index('TVOLNO',inplace=True)
    schematic = schematic.loc[catchment_ids(uci.network.G)]
    
    dfs = []
    for operation in ['PERLND','IMPLND']:
        df = schematic.loc[schematic['SVOL'] == operation].reset_index()
        df = df.set_index('SVOLNO')
        dfs.append(df.join(uci.table(operation,'GEN-INFO').iloc[:,0]))
    
    df = pd.concat(dfs).reset_index()
    df = df.set_index('TVOLNO')
    return df

def subwatershed(uci,reach_id):
    return subwatersheds(uci).loc[[reach_id]]

def drains_to(uci,opnid,operation):
    schematic = uci.table('SCHEMATIC').set_index('SVOL')
    schematic = schematic[schematic.index == operation]
    schematic = schematic[schematic['TVOL'] == 'RCHRES'][['SVOLNO','TVOLNO','AFACTR']].astype({'SVOLNO':int,'TVOLNO':int,'AFACTR':float})
    schematic = schematic[schematic['TVOLNO'] == opnid]
    return schematic

def landcover_area(uci):
    return pd.concat([operation_area(uci,operation) for operation in ['PERLND','IMPLND']])

def operation_area(uci,operation):
    # schematic = uci.table('SCHEMATIC').copy()
    # schematic = schematic.astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR':float})
    # schematic = schematic.groupby(['SVOL','SVOLNO']).sum()
    # schematic = schematic.loc[[operation]].droplevel(0)['AFACTR'].to_frame()
    df = subwatersheds(uci)
    df = df.loc[df['SVOL'] == operation,['AFACTR','SVOLNO']]
    df = df.set_index('SVOLNO')
    df['LSID'] = uci.table(operation,'GEN-INFO').iloc[:,0].loc[df.index].values
    return df








# p = paths(G,reach_id,'RCHRES') 
# ptotout = hbn.get_multiple_timeseries('RCHRES',4,'PTOTOUT',reach_ids)
# ptotin = hbn.get_multiple_timeseries('RCHRES',4,'PTOTIN',reach_ids)
# reach_losses = 1-(ptotin-ptotout)/ptotin
# loads = subwatershed_total_phosphorous_loading(uci,hbn,t_code=4)

# loss_factors = pd.concat([reach_losses[v].prod(axis=1) for k,v in p.items()],axis=1)
# loss_factors.columns = list(p.keys())
# allocations = loads[loss_factors.columns].mul(loss_factors.values,axis=1)



# def loss_factor(G,reach_id,reach_losses):
#     p = paths(G,reach_id,'RCHRES')
#     loss_factors = pd.concat([reach_losses[v].prod(axis=1) for k,v in p.items()],axis=1)
#     loss_factors.columns = list(p.keys())
    
#     return return_loss_factors

# def allocation(uci,reach_id):
    
    
    
    
#     subwatersheds = uci.network.subwatersheds()
#     load = total_phosphorous(uci,hbn,4)
#     load[subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']['SVOLNO'].to_list()]
    

# def catchment_area(G,reach_id):
#     node = G.labels[('RCHRES',reach_id)]
#     return [attributes['area'] for _,_, attributes in G.in_edges(node, data=True) if 'area' in attributes.keys()]
                




         
        
# def upstream_reach(G,reach_id):
#     node = G.labels[('RCHRES',reach_id)]
#     upstream_reach_ids = [node for node in list(G.predecessors(node)) if G.nodes[node]['type'] == 'RCHRES']
#     return upstream_reach_ids

        
# def downstream_reachs(G,reach_id):
#     node = G.labels[('RCHRES',reach_id)]
#     downstream_reach_ids = [node for node in list(G.successors(node)) if G.nodes[node]['type'] == 'RCHRES']
#     return downstream_reach_ids




    
#     neighbors = list(G.predecessors(427))
#     upstream_reach_ids = [node for node,operation in nx.get_node_attributes(G,'operation').items() if (operation == 'RCHRES') & (node in neighbors)]
    
#     upstream_reach_nodes = [node for node in nx.neighbors(G,node) if 'operation' in node.keys() &
#     subset_graph



# def upstream_network(G,reach_id):
#     G = deepcopy(G)
#     ancestors = list(nx.ancestors(G,reach_id))
#     ancestors.insert(0,reach_id)
#     drop = [node for node in G.nodes if node not in ancestors]
#     G.remove_nodes_from(drop)
#     return G

# def downstream_network(G,reach_id):
#     G = deepcopy(G)
#     descendants = list(nx.descendants(G,reach_id))
#     drop = [node for node in G.nodes if node not in descendants]
#     G.remove_nodes_from(drop)
#     return G
 
    
# def subset_graph(G,reach_id, upstream_reach_ids = None):
#     G = upstream_network(G,reach_id)
#     if upstream_reach_ids is not None:
#         [G.remove_nodes_from(nx.ancestors(G,upstream_reach_id)) for upstream_reach_id in upstream_reach_ids if upstream_reach_id in G.nodes]
#         [G.remove_nodes_from([upstream_reach_id]) for upstream_reach_id in upstream_reach_ids if upstream_reach_id in G.nodes]
#     assert([len(sinks(G)) == 0,sinks(G)[0] == reach_id])
#     return G

# def sinks(G):
#     return [node for node in G.nodes if (G.out_degree(node) == 0)]




# -*- coding: utf-8 -*-
"""
Created on Thu Feb  6 14:50:45 2025

@author: mfratki
"""

import networkx as nx
import pandas as pd
import numpy as np
import math
from itertools import chain

from hspf.model import uci
from hspf.model.topology import ModelTopology, afactr_semantics
from hspf.core.types import OperationKey

def create_graph(topology: ModelTopology,
                 include_land: bool = True) -> nx.MultiDiGraph:

    G = nx.MultiDiGraph()
    
    # Generate nodes


    nodes = [
        (OperationKey(row["OPERATION"], row["OPNID"]), row) 
        for row in topology.operations.to_dict('records') if row['in_opn_sequence']
    ]

    if not include_land:
        nodes = [
            (OperationKey(row["OPERATION"], row["OPNID"]), row) 
            for row in topology.operations.to_dict('records') if row['in_opn_sequence'] and row['OPERATION'] == 'RCHRES'
        ]
    # Bulk-add nodes (faster than a for loop)
    G.add_nodes_from(nodes)

    node_operations = list({node.operation: None for node in G.nodes}.keys())
    edges = topology.runnable_connections()
    mask = (
        (edges['SVOL'].isin(node_operations)) &
        (edges['TVOL'].isin(node_operations)))
    edges = edges[mask]

    # Iterate over lightweight python dicts instead of slow pandas Series
    for row in edges.to_dict('records'):
        source = OperationKey(row["SVOL"], row["SVOLNO"])
        target = OperationKey(row["TVOL"], row["TVOLNO"])
        
        semantic = afactr_semantics(row['SVOL'])
        row[semantic] = row.get('AFACTR')
        G.add_edge(source, target, **row)

    return G


def watershed_reach_ids(G,reach_ids,upstream_reach_ids = None):
    '''
    Creates a sugraph representing the the catchments upstream of the specified hspf model reaches. Note that a negative reach_ids indicate to subtract that area from the total.

    ''' 

    keys = [OperationKey('RCHRES', reach_id) for reach_id in reach_ids]
    
    # 1. Initialize and collect all upstream reaches
    all_upstream_reaches = set()
    for node_id in keys:
        ancestor_reaches = [node for node in nx.ancestors(G,node_id) if node.operation == 'RCHRES']
        
        all_upstream_reaches.update(ancestor_reaches) # Add ancestors to the combined set
    all_upstream_reaches.update([key for key in keys]) # Include the target nodes themselves

    if upstream_reach_ids is not None:
        upstream_keys = [OperationKey('RCHRES', reach_id) for reach_id in upstream_reach_ids]
        for node_id in upstream_keys:
            all_upstream_reaches = all_upstream_reaches - set([node for node in nx.ancestors(G,node_id) if node.operation == 'RCHRES']) - {node_id}
    else:
        upstream_keys = set()

    return all_upstream_reaches


def paths(G,reach_id,source_type = 'RCHRES'):
    target_node = OperationKey('RCHRES', reach_id)
    ancestors = [node for node in nx.ancestors(G,target_node) if node.operation == source_type] 
    return {source.opnid:[node.opnid for node in nx.shortest_path(G,source,target_node)] for source in ancestors} | {reach_id: [reach_id]}


#%% Legacy Methods for Backwards compatability
class Network():
    def __init__(self, topology : ModelTopology):
        self.topology = topology
        self.G = create_graph(self.topology)
        self.catchment_ids = list(set(self.topology.land_to_reach()['TVOLNO'].to_list()))
        self.routing_reaches = self._routing_reaches()
        self.lakes = self._lakes()

    def _upstream(self,reach_id,node_type = 'RCHRES'):
        '''
        Returns list of model reaches upstream of inclusive of reach_id

        '''
        #upstream = [node['type_id'] for node in upstream_nodes(self.G,reach_id,node_type) if node['type'] == 'RCHRES']
        #upstream.append(reach_id)
        upstream = [node.opnid for node in nx.ancestors(self.G,('RCHRES', reach_id)) if node.operation == node_type]
        upstream.append(reach_id)
        return upstream

    def _downstream(self,reach_id,node_type = 'RCHRES'):
        '''
        Returns list of model reaches downstream inclusive of reach_id

        '''
                    # downstream = [node['type_id'] for node in downstream_nodes(self.G,reach_id,node_type) if node['type'] == node_type]
                    # downstream.insert(0,reach_id)
        downstream = [node.opnid for node in nx.descendants(self.G,('RCHRES', reach_id)) if node.operation == node_type]
        downstream.insert(0,reach_id)
        return downstream
        


    def calibration_order(self,reach_nodes = None):
        '''
        Determines the order in which the model reaches should be calibrated to
        prevent upstream influences. Primarily helpful when calibrating sediment and
        adjusting in channel erosion rates.
        '''
        
        # No need to .copy() anymore since we aren't deleting nodes
        if reach_nodes is None:
            reach_nodes = [node for node in self.G if node.operation == 'RCHRES']
        sub_G = self.G.subgraph(reach_nodes) 
        
        order = []
        for generation in nx.topological_generations(sub_G):
            # generation is a list of node IDs at the current topological level
            order.append([node.opnid for node in generation])
            
        return order    
    
    def station_order(self,reach_ids):
        raise NotImplementedError()
        
    
    def downstream(self,reach_id):
        '''
        Downstream adjacent reaches

        '''
        return [node.opnid for node in self.G.successors(('RCHRES', reach_id)) if node.operation == 'RCHRES']
    
    def upstream(self,reach_id):
        '''
        Upstream adjacent reaches

        '''
        return [node.opnid for node in self.G.predecessors(('RCHRES', reach_id)) if node.operation == 'RCHRES']
        
    def get_opnids(self,operation,reach_ids, upstream_reach_ids = None):
        '''
        Operation IDs with a path to reach_id. Operations upstream of upstream_reach_ids will not be included

        '''
        reach_ids = watershed_reach_ids(self.G,reach_ids,upstream_reach_ids)
        
        mask = (
                (self.topology.connections['TVOL'] == 'RCHRES') & 
                (self.topology.connections['TVOLNO'].isin(reach_ids)) & 
                (self.topology.connections['SVOL'] == operation)
            )

        result = list(self.topology.connections.loc[mask, 'SVOLNO'].unique())
        return result
    
    def operation_area(self,operation,opnids = None):
        '''
        Area of operation type for specified operation IDs. If None returns all operation areas.
        Equivalent to the schematic table filtered by operation and opnids.
        '''
        df = self.subwatersheds()
        mask = df['SVOL'] == operation
        if opnids is not None:
            mask &= df['SVOLNO'].isin(opnids)

        df = df.loc[mask,['AFACTR','SVOLNO']]
        df = df.set_index('SVOLNO')
        return df 
        

    def subwatersheds(self,reach_ids = None):
        subwatersheds = self.topology.land_to_reach()
        operations = self.topology.operations

        subwatersheds = pd.merge(subwatersheds,operations[['OPERATION','OPNID','LSID']],
                                 left_on = ['SVOL','SVOLNO'],
                                 right_on = ['OPERATION','OPNID'],
                                 how='left')

        if reach_ids is not None:
            subwatersheds = subwatersheds.loc[subwatersheds.index.isin(reach_ids)]
        
        subwatersheds.set_index('TVOLNO', inplace=True)
        return subwatersheds    
    
    def subwatershed_area(self,reach_id):
        area = self.subwatershed(reach_id)['AFACTR'].sum()
        # if (reach_id in self.lakes()) & (f'FTABLE{reach_id}' in self.uci.table_names('FTABLES')):
        #     area = area + self.lake_area(reach_id)
        return area
    
    def drains_from(self,operation,opnids):
        runnable_connections = self.topology.runnable_connections()
        mask = (
            (runnable_connections['TVOL'] == 'RCHRES') & 
            (runnable_connections['SVOLNO'].isin(opnids)) & 
            (runnable_connections['SVOL'] == operation)
        )
        result = runnable_connections[mask][['AFACTR','SVOL','SVOLNO','TVOLNO']].groupby(['SVOL','SVOLNO','TVOLNO']).sum()
        return result

    def drains_to(self,reach_ids,source_operation):
        subwatersheds = self.topology.land_to_reach()
        mask = (
            (subwatersheds['TVOL'] == 'RCHRES') & 
            (subwatersheds['TVOLNO'].isin(reach_ids)) & 
            (subwatersheds['SVOL'] == source_operation)
        )
        subwatersheds = subwatersheds[mask]
        subwatersheds = subwatersheds[['SVOL','SVOLNO','TVOLNO','AFACTR']]
        return subwatersheds.groupby(['SVOL','SVOLNO','TVOLNO']).sum()

    
    def drainage_area(self,reach_ids,upstream_reach_ids = None):
        catchment_ids = watershed_reach_ids(self.G,reach_ids,upstream_reach_ids)
        catchments = self.topology.land_to_reach()
        
        mask = catchments['TVOLNO'].isin(catchment_ids)
        
        catchments = catchments.loc[mask]
        return catchments['AFACTR'].sum()
    
    def drainage_area_landcover(self,reach_ids,upstream_reach_ids = None, group = True):
        catchment_ids = watershed_reach_ids(self.G,reach_ids,upstream_reach_ids)
        catchments = self.subwatersheds(catchment_ids)
        areas = catchments.groupby(['SVOL','SVOLNO','LSID'])['area'].sum()
        if group:  
            areas = areas.groupby(['SVOL','LSID']).sum()
        return areas

    def outlets(self):
        nodes = [node for node in self.G.nodes if node.operation == "RCHRES"]
        return [node.opnid for node, out_degree in self.G.subgraph(nodes).out_degree() if (out_degree == 0) & (node.operation == 'RCHRES')]

    def _lakes(self):
        mask = self.topology.operations['LKFG'] == 1
        return self.topology.operations.loc[mask].index.astype(int).to_list()

    def lake_area(self,reach_id):
        #return self.uci.table('FTABLES',f'FTABLE{reach_id}')['Area'].max()
        raise NotImplementedError("lake_area method is not implemented yet.")
    
    def _routing_reaches(self):
        operations = self.topology.operations
        mask = (operations['OPERATION'] == 'RCHRES')
        operations = operations.loc[mask]
        return [reach_id for reach_id in operations['OPNID'].to_list() if reach_id not in self.catchment_ids]

    def paths(self,reach_id):
        return paths(self.G,reach_id)
    

def drains_to(topology: ModelTopology,reach_ids,source_operation):
    subwatersheds = topology.land_to_reach()
    mask = (
        (subwatersheds['TVOL'] == 'RCHRES') & 
        (subwatersheds['TVOLNO'].isin(reach_ids)) & 
        (subwatersheds['SVOL'] == source_operation)
    )
    subwatersheds = subwatersheds[mask]
    subwatersheds = subwatersheds[['SVOL','SVOLNO','TVOL','AFACTR']]
    return subwatersheds.groupby(['SVOL','SVOLNO','TVOL']).sum()


# def collect(G,reach_id,upstream_reach_ids):
#     def _collect(G,reach_id,upstream_reach_ids,result):
#         _upstream_reaches = upstream_adjacent_reachs(G,reach_id)
#         for upstream_reach_id in _upstream_reaches:
#             if upstream_reach_id not in upstream_reach_ids:
#                 _collect(G,upstream_reach_id,upstream_reach_ids,result)
#                 result.add(upstream_reach_id)
#         return result
    
#     result = _collect(G,reach_id,upstream_reach_ids,set())
#     result.add(reach_id)
#     return result

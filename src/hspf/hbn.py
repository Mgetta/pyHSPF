# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 15:33:52 2022
Utility functions for accessing data from the hbn files as they relate to the
nutrients relevant for our current calibration methods. (See calibration_helpers.py)

This module provides high-level data processing for HSPF Binary (HBN) files.
The low-level binary parsing has been separated into hbn_parser.py for improved
testability and separation of concerns.

@author: mfratki
"""
from hspf import helpers
from hspf import hbn_parser
import pandas as pd
import math
from struct import unpack
from numpy import fromfile
from pandas import DataFrame
from datetime import datetime, timedelta #, timezone
from collections import defaultdict
from collections.abc import MutableMapping
#from pathlib import Path


#TIMSERIES_CATALOG = Path('C:/Users/mfratki/Documents/GitHub/hspf_tools/parser/Timeseries Catalog')

# catalog = []
# columns = ['operation','activity','name', 'sub1','sub2','type','units_eng','units_met','comments']
# for operation in ['PERLND','IMPLND','RCHRES']:
#     files = [file for file in TIMSERIES_CATALOG.joinpath(operation).iterdir()]
#     for file in files:
#         lines = open(file).readlines()
#         for line in lines:
#             values = [col for col in line.split(' ') if col != '']
#             comments = ' '.join(values[6:]).strip('\n')
#             values = values[0:6]
#             values.append(comments)
#             values.insert(0,file.stem)
#             values.insert(0,operation)
#             catalog.append(pd.Series(data = values,index = columns))
            
# df = pd.concat(catalog,axis=1).transpose()


# TIMESERIES_CATALOG = pd.read_csv('C:/Users/mfratki/Documents/GitHub/hspf_tools/parser/Timeseries Catalog/TIMSERIES_CATALOG.csv')


# def timeseries_info(t_opn,t_activity,t_cons):
#     ts_catalog = TIMESERIES_CATALOG.loc[(TIMESERIES_CATALOG['operation'] == t_opn) &
#                            (TIMESERIES_CATALOG['activity'] == t_activity)]
    
#     ts_info = [row for index,row in ts_catalog.iterrows() if t_cons.startswith(row['name'])]
    
#     assert(len(ts_info) <= 1)
#     return ts_info

CF2CFS = {'hourly':3600,
          'daily':86400,
          'monthly':2592000,
          'yearly':31536000,
          'h':3600,
          'D':86400,
          'ME':2592000,
          'Y':31536000,
          'YE':31536000,
          2:3600,
          3:86400,
          4:2592000,
          5:31536000}

AGG_DEFAULTS = {'cfs':'mean',
                'mg/l':'mean',
                'degF': 'mean',
                'lb':'sum'}

UNIT_DEFAULTS = {'Q': 'cfs',
                 'TSS': 'mg/l',
                 'TP' : 'mg/l',
                 'OP' : 'mg/l',
                 'TKN': 'mg/l',
                 'N'  : 'mg/l',
                 'WT' : 'degF',
                 'WL' : 'ft'}

#agg_func = AGG_DEFAULTS[unit]
def get_simulated_implnd_constituent(hbn,constituent,time_step):
    t_cons = helpers.get_tcons(constituent,'IMPLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='IMPLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'IMPLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df


def get_simulated_perlnd_constituent(hbn,constituent,time_step):
    t_cons = helpers.get_tcons(constituent,'PERLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='PERLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'PERLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df

def get_catchment_constituent(hbn,constituent,catchment_ids = None,time_step = 5):
    if constituent == 'Q':
        units = 'in/acre'
    else:
        units = 'lb/acre'
    
    perlnds = hbn.get_perlnd_constituent(constituent).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    perlnds['OPERATION'] = 'PERLND'
    implnds = hbn.get_implnd_constituent(constituent).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    implnds['OPERATION'] = 'IMPLND'

    df = pd.concat([perlnds,implnds],axis=0)
    df['unit'] = units 
    df.rename(columns = {'index':'datetime','value':constituent},inplace = True)
    return df

        
def get_simulated_flow(hbn,time_step,reach_ids,unit = None):
    
    if unit is None:
        unit = 'cfs'
    assert unit in ['cfs','acrft']

    # if sign is None:
    #     exclude = [1 for i in enumerate(reach_ids)]
    sign = [math.copysign(1,reach_id) for reach_id in reach_ids]
    reach_ids = [abs(reach_id) for reach_id in reach_ids]
    
    flows = hbn.get_multiple_timeseries('RCHRES',time_step,'ROVOL',reach_ids)
    flows = (flows*sign).sum(axis=1) # Correct instances when a flow needs to be subtracted (rare)
    
    if unit == 'cfs':
        flows = flows/CF2CFS[time_step]*43560 #Acrfeet/invl to cubic feet/s
    
    flows.attrs['unit'] = unit
    return flows

def get_simulated_temperature(hbn,time_step,reach_ids):
    assert len(reach_ids) == 1, "Temperature can only be retreived for one reach at a time."


    wt = hbn.get_multiple_timeseries('RCHRES',time_step,'TW', reach_ids)
    wt = wt.sum(axis=1)
    wt.attrs['unit'] = 'degf'
    
    return wt
    

def get_simulated_reach_constituent(hbn,constituent,time_step,reach_ids,unit = None):
    # if exclude is None:
    #     exclude = [1 for i in enumerate(reach_ids)]
    sign = [math.copysign(1,reach_id) for reach_id in reach_ids]

    if unit is None:
        unit = UNIT_DEFAULTS[constituent]
    else:
        assert(unit in ['mg/l','lb'])
        
    t_cons = helpers.get_tcons(constituent,'RCHRES','lb')
    
    # Correct instances when a reach output needs to be subtracted (rare)
    df = pd.concat([hbn.get_multiple_timeseries('RCHRES',time_step,t_con,[abs(reach_id) for reach_id in reach_ids])*sign for t_con in t_cons],axis=1).sum(axis=1)
    
    if constituent == 'TSS':
        df = df*2000
    
    
    if unit == 'mg/l':
        #if time_step not in ['h','hourly']:
        flow = get_simulated_flow(hbn,time_step,reach_ids,'acrft')*1233481.8375475 #(acrft to Liters)
        df = df*453592.37 # lbs to mg/l
        df = df/flow
    
    df.attrs['unit'] = unit
    df.attrs['constituent'] = constituent
    df.attrs['reach_ids'] = reach_ids
    return df
    
class hbnInterface:
    def __init__(self,file_paths,Map = True):
        self.names = [file_path for file_path in file_paths]
        self.hbns = [hbnClass(file_path,Map) for file_path in file_paths]
        
    def _clear_cache(self):
        [hbn._clear_cache() for hbn in self.hbns]
        

        
    def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        df = pd.concat([hbn._get_time_series(t_opn, t_cons, t_code, opnid, activity) for hbn in self.hbns],axis = 1)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
        
        if long_format:
            df = df.reset_index().melt(id_vars = ['index'],var_name = 'OPNID',value_name = t_con)
            df.rename(columns = {'index':'datetime'},inplace = True)
            df['OPERATION'] = t_opn
        return df
        
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None,axis = 1,long_format = False):
        df = pd.concat([hbn._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity) for hbn in self.hbns],axis = 1)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
        
        if long_format:
            df = df.reset_index().melt(id_vars = ['index'],var_name = 'OPNID',value_name = 'value')
            df.rename(columns = {'index':'datetime'},inplace = True)
            df['TIMESERIES'] = t_con
            df['OPERATION'] = t_opn
        return df

    def get_perlnd_constituent(self,constituent,perlnd_ids = None,time_step = 5):
        return get_simulated_perlnd_constituent(self,constituent,time_step)

    def get_implnd_constituent(self,constituent,implnd_ids = None,time_step = 5):
        return get_simulated_implnd_constituent(self,constituent,time_step)

        
    def get_reach_constituent(self,constituent,reach_ids,time_step,unit = None):
        if constituent == 'Q':
            df = get_simulated_flow(self,time_step,reach_ids,unit = unit)
        elif constituent == 'WT':
            df = get_simulated_temperature(self,time_step,reach_ids)
        else:     
            df = get_simulated_reach_constituent(self,constituent,time_step,reach_ids,unit)
        return df.to_frame()
    
    def output_names(self):
        # dd = defaultdict(list)    
        # dics =  [hbn.output_names() for hbn in self.hbns]
        # for dic in dics:
        #     for key, vals in dic.items():
        #         [dd[key].append(val) for val in vals]
        # dd = defaultdict(set)    
        dics =  [hbn.output_names() for hbn in self.hbns]
        return merge_dicts(dics)
        # for dic in dics:
        #     for operation, vals in dic.items():
        #         for activity,v in vals.items():
        #             [dd[operation][activity].add(t) for t in v]
        # return dd

    def _timeseries(self):
        mapn = self._mapn()
        timeseries = []
        for key, vals in mapn.items():
            _key = list(key)
            for val in vals:
                timeseries.append(_key + [val])
        return timeseries      
            

    def _mapn(self):
        dd = defaultdict(set)    
        dics =  [hbn.mapn for hbn in self.hbns]
        for dic in dics:
            for key, vals in dic.items():
                [dd[key].add(val) for val in vals]
        return dd 
    
    def get_perlnd_data(self,constituent,t_code = 'yearly'):
        t_cons = helpers.get_tcons(constituent,'PERLND')
        
        df = pd.concat([self.get_multiple_timeseries(t_opn = 'PERLND',
                                     t_code = t_code,
                                     t_con = t_con,
                                     opnids = None)
                         for t_con in t_cons],axis = 0)
        
        return df
         
          
    def get_rchres_output(self,constituent,units = 'mg/l',t_code = 5):
        '''
        Convience function for accessing the hbn time series associated with our current
        calibration method. Assumes you are summing across all dataframes.
       '''
        t_cons = helpers.get_tcons(constituent,'RCHRES',units)
        df = sum([self.get_multiple_timeseries('RCHRES',t_code,t_con) for t_con in t_cons])
        df.attrs['unit'] = units
        df.attrs['constituent'] = constituent
        return df
    
        
    def reach_losses(self,constituent,t_code): 
        inflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][0]],axis=1).sum()
        outflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][1]],axis=1).sum()
        return inflows/outflows
        
LOSS_MAP = {'Q':(['IVOL'],['ROVOL']),
       'TSS': (['ISEDTOT'],['ROSEDTOT']),
       'TP': (['PTOTIN'],['PTOTOUT']),
       'N': ([ 'NO2INTOT', 'NO3INTOT'],['NO3OUTTOT','NO2OUTTOT']),
       'TKN':(['TAMINTOT','NTOTORGIN'],['TAMOUTTOT','NTOTORGOUT']),
       'OP': (['PO4INDIS'],['PO4OUTDIS'])}
TCODES2FREQ = {1:'min',2:'h',3:'D',4:'M',5:'Y'}
    
class hbnClass:
    """
    Class for reading and processing HSPF Binary (HBN) files.
    
    This class provides methods for accessing time series data from HBN files.
    The low-level binary parsing is delegated to the hbn_parser module for
    improved testability and separation of concerns.
    
    Attributes:
        file_name: Path to the HBN file.
        data: Raw binary data from the file.
        mapn: Dictionary mapping (operation, id, activity) to constituent names.
        mapd: Dictionary mapping (operation, id, activity, tcode) to data locations.
        tcodes: Dictionary for time code conversions.
        pandas_tcodes: Dictionary mapping time codes to pandas frequency strings.
    """
    
    def __init__(self, file_name, Map=True):
        """
        Initialize hbnClass with an HBN file.
        
        Args:
            file_name: Path to the HBN file to read.
            Map: If True, parse the file structure on initialization.
        """
        self._load_data(file_name, Map)
        self.tcodes = {'minutely':1,'hourly':2,'daily':3,'monthly':4,'yearly':5, 
                       1:'minutely',2:'hourly',3:'daily',4:'monthly',5:'yearly',
                       'min':1,'h':2,'D':3,'M':4,'Y':5,'H':2,'ME':4,'YE':5}
        self.pandas_tcodes = {1:'min',2:'h',3:'D',4:'ME',5:'YE'}
    
    def _load_data(self, file_name, Map=False):
        """
        Load and optionally parse an HBN file.
        
        This method uses the hbn_parser module for file validation and parsing,
        separating the low-level binary parsing from data processing.
        
        Args:
            file_name: Path to the HBN file.
            Map: If True, parse the file structure.
        """
        self.file_name = file_name
        
        # Use parser module to parse the file
        parse_result = hbn_parser.parse_hbn_file(file_name)
        
        if not parse_result.is_valid:
            print(parse_result.error_message)
            return
        
        # Store the raw data and parsed structures
        self.data = parse_result.raw_data
        
        if Map:
            # Use the parsed mapn and mapd directly
            self.mapn = parse_result.mapn
            self.mapd = parse_result.mapd
            self._initialize_cache()
        else:
            self._clear_cache()
    
    # Legacy method name for backward compatibility
    def data(self, file_name, Map=False):
        """Legacy method - use _load_data instead."""
        self._load_data(file_name, Map)
    
    def _initialize_cache(self):
        """Initialize the data cache structures."""
        self.simulation_duration_count = 0
        self.data_frames = {}
        self.summary = []
        self.summarycols = ['Operation', 'Activity', 'segment', 'Frequency', 'Shape', 'Start', 'Stop']
        self.summaryindx = []
        self.output_dictionary = {}
    
    def map_hbn(self):
        """
        Parse the HBN file structure.
        
        This method now delegates to hbn_parser.parse_hbn_file() for the actual
        parsing, maintaining backward compatibility while using the separated
        parsing logic.
        
        Returns:
            None. Sets self.mapn and self.mapd as side effects.
        """
        # Re-parse the file using the parser module
        parse_result = hbn_parser.parse_hbn_file(self.file_name)
        
        if not parse_result.is_valid:
            print(parse_result.error_message)
            return
        
        self.mapn = parse_result.mapn
        self.mapd = parse_result.mapd
        self._initialize_cache()

    
    def read_data(self, operation, id, activity, tcode):
        """
        Read time series data for a specific operation/activity/segment.
        
        This method uses the hbn_parser module for the low-level data extraction,
        keeping this class focused on data processing and caching.
        
        Args:
            operation: Operation type (PERLND, IMPLND, RCHRES)
            id: Segment identifier
            activity: Activity type (HYDR, PWATER, etc.)
            tcode: Time code for temporal resolution
            
        Returns:
            DataFrame with the time series data, or None if no data found.
        """
        column_names = self.mapn[operation, id, activity]
        mapd_entries = self.mapd[operation, id, activity, tcode]
        
        # Use parser module for low-level data extraction
        times, rows = hbn_parser.read_timeseries_data(
            self.data, 
            mapd_entries, 
            column_names
        )
        
        dfname = f'{operation}_{activity}_{id:03d}_{tcode}'
        if self.simulation_duration_count == 0:
            self.simulation_duration_count = len(times)
            
        df = DataFrame(rows, index=times, columns=column_names).sort_index(level='index')
        
        if len(df) > 0:
            self.summaryindx.append(dfname)
            self.summary.append((operation, activity, str(id), self.tcodes[tcode], str(df.shape), df.index[0], df.index[-1]))
            self.output_dictionary[dfname] = column_names
            # Resample to set hours to 00 for non-hourly time steps
            self.data_frames[dfname] = df.resample(self.pandas_tcodes[tcode]).mean()
            return self.data_frames[dfname]
        else:
            return None
    
    def _clear_cache(self):
        """Clear all cached data frames and summaries."""
        self.data_frames = {}
        self.summary = []
        self.summarycols = ['Operation', 'Activity', 'segment', 'Frequency', 'Shape', 'Start', 'Stop']
        self.summaryindx = []
        self.output_dictionary = {}

    # def read_data2(self,operation,id,activity,tcode):

    #     rows = []
    #     times = []
        
    #     nvals = len(self.mapn[operation, id, activity])  # number of constituent time series
    #     #utc_offset = timezone(timedelta(hours=6))  # UTC is 6 hours ahead of CST
        
    #     indices, reclens = zip(*self.mapd[operation, id, activity, tcode])
    #     indices = np.array(indices)
    #     data_array = np.frombuffer(self.data, dtype=np.uint8)  # Convert raw data to NumPy array
    
    #     times = [np.frombuffer(data_array[indice+36:  indice+56], dtype=np.int32,count=5) for indice in indices]
    #     times = [datetime(time[0],time[1],time[2],time[3]-1) for time in times]
    #     rows =  [np.frombuffer(data_array[indice + 56:indice +56 + (4 * nvals)], dtype=np.float32) for indice in indices]
    
    #     df = pd.DataFrame(rows, index=times, columns=self.mapn[operation, id, activity]).sort_index(level = 'index')
    #     return df
   
    def infer_opnids(self,t_opn, t_cons,activity):
        result = [k[-2] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn) & (k[-1] == activity)]
        if len(result) == 0:
            result = [-1]
        #     return print('No Constituent-OPNID relationship found')
        return result
    
    
    def infer_activity(self,t_opn, t_cons):  
        result = [k[-1] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn)]
        if len(result) == 0:
            result = ''
        else:#     return print('No Constituent-Activity relationship found')
            assert(len(set(result)) == 1)
            result = result[0]
        return result
    
    def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        df = self._get_time_series(t_opn, t_cons, t_code, opnid, activity)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
        return df

    def _get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        """
        get a single time series based on:
        1.      t_opn: RCHRES, IMPLND, PERLND
        2.   t_opn_id: 1, 2, 3, etc
        3.     t_cons: target constituent name
        4. t_activity: HYDR, IQUAL, etc
        5.  time_unit: yearly, monthly, full (default is 'full' simulation duration)
        """


        if isinstance(t_code,str):
            t_code = self.tcodes[t_code]
        
        if activity is None:
            activity = self.infer_activity(t_opn,t_cons)        

            
        summaryindx = f'{t_opn}_{activity}_{opnid:03d}_{t_code}'
        if summaryindx in self.summaryindx:
            df = self.data_frames[summaryindx][t_cons].copy()
            #df.index = df.index.shift(-1,TCODES2FREQ[t_code])
            df = df[df.index >= '1996-01-01']
            
        elif (t_opn, opnid, activity,t_code) in self.mapd.keys():
            df =  self.read_data(t_opn,opnid,activity,t_code)[t_cons].copy()
            #df.index = df.index.shift(-1,TCODES2FREQ[t_code])
            df = df[df.index >= '1996-01-01']
        else:
            df = pd.DataFrame()
            
        return df
    
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
        df = self._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
        return df
    
    def _get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
        # a single constituent but multiple opnids

        
        if isinstance(t_code,str):
            t_code = self.tcodes[t_code]
            
        if activity is None:
            activity = self.infer_activity(t_opn,t_con)   

        if opnids is None:
            opnids = self.infer_opnids(t_opn,t_con,activity)

           
        df = pd.DataFrame()
        frames = []
        mapd_list = list(self.mapd.keys())
        for opnid in opnids:
            if (t_opn,opnid,activity,t_code) in mapd_list:
                frames.append(self.get_time_series(t_opn,t_con,t_code,opnid,activity).rename(opnid))
        if len(frames)>0:
            df = pd.concat(frames,axis=1)
        
        return df
    
    def output_names(self):
        activities = set([k[-1] for k,v in self.mapn.items()])
        dic = {}
        for activity in activities:
            t_cons = [v for k,v in self.mapn.items() if k[-1] == activity]   
            dic[activity] = set([item for sublist in t_cons for item in sublist])
        return dic
    

    def output_names(self):

        activities = []
        operations = []
        for k, v in self.mapn.items():
            operations.append(k[0])
            activities.append(k[-1])

        operations = set(operations)
        activities = set(activities)
        #activities = set([k[-1] for k,v in self.mapn.items()])

        dic = {}
        for operation in operations:
            acitivities = set([k[-1] for k,v in self.mapn.items() if k[0] == operation])
            dic[operation] = {}
            for activity in acitivities:
                t_cons = [v for k,v in self.mapn.items() if (k[0] == operation) & (k[-1] == activity)]   
                dic[operation][activity] = set([item for sublist in t_cons for item in sublist])
        # for activity in activities:
        #     t_cons = [v for k,v in self.mapn.items() if k[-1] == activity]   
        #     dic[activity] = set([item for sublist in t_cons for item in sublist])
        return dic
    
    def get_timeseries(self):
        mapn = self.mapn
        timeseries = []
        for key, vals in mapn.items():
            _key = list(key)
            for val in vals:
                timeseries.append(_key + [val])
        return timeseries      

    @staticmethod          
    def get_perlands(summary_indxs):
         perlands =  [int(summary_indx.split('_')[-2]) for summary_indx in summary_indxs]
         return perlands
     

def merge_dicts(dicts):
    """
    Merge a list of dictionaries into a single dictionary, combining sets
    at the leaf level and properly merging nested dictionaries.
    
    Args:
        dicts (list): A list of dictionaries to merge.
    
    Returns:
        dict: The merged dictionary.
    """
    def recursive_merge(d1, d2):
        for key, value in d2.items():
            if key in d1:
                # If the value is a dictionary, recurse
                if isinstance(d1[key], MutableMapping) and isinstance(value, MutableMapping):
                    recursive_merge(d1[key], value)
                # If the value is a set, merge the sets
                elif isinstance(d1[key], set) and isinstance(value, set):
                    d1[key].update(value)
                else:
                    raise ValueError(f"Incompatible types for key '{key}': {type(d1[key])} vs {type(value)}")
            else:
                # If the key does not exist in d1, copy it
                d1[key] = value
    
    # Start with an empty dictionary
    merged_dict = {}
    
    for d in dicts:
        recursive_merge(merged_dict, d)
    
    return merged_dict

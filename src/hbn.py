# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 15:33:52 2022
Utility functions for accessing data from the hbn files as they relate to the
nutrients relevant for our current calibration methods. (See calibration_helpers.py)

@author: mfratki
"""
from hspf_tools.calibrator import calibration_helpers as ch 
import pandas as pd
import math
from struct import unpack
from numpy import fromfile
from pandas import DataFrame
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import numpy as np
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
    t_cons = ch.get_tcons2(constituent,'IMPLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='IMPLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'IMPLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df


def get_simulated_perlnd_constituent(hbn,constituent,time_step):
    t_cons = ch.get_tcons2(constituent,'PERLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='PERLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'PERLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df

def get_simulated_catchment_constituent(hbn,constituent,time_step):
    return pd.concat([get_simulated_perlnd_constituent(hbn,constituent,time_step),
                      get_simulated_implnd_constituent(hbn,constituent,time_step)])
        
        
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

def get_simulated_temperature(hbn,units,time_step,reach_ids):
    raise NotImplementedError()
    

def get_simulated_reach_constituent(hbn,constituent,time_step,reach_ids,unit = None):
    # if exclude is None:
    #     exclude = [1 for i in enumerate(reach_ids)]
    sign = [math.copysign(1,reach_id) for reach_id in reach_ids]

    if unit is None:
        unit = UNIT_DEFAULTS[constituent]
    else:
        assert(unit in ['mg/l','lb','cfs','degF'])
        
    t_cons = ch.get_tcons2(constituent,'RCHRES','lb')
    
    # Correct instances when a flow needs to be subtracted (rare)
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
        return pd.concat([hbn.get_time_series(t_opn, t_cons, t_code, opnid, activity) for hbn in self.hbns],axis = 1)
        
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None,axis = 1):
        return pd.concat([hbn.get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity) for hbn in self.hbns],axis = 1)

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
        dd = defaultdict(set)    
        dics =  [hbn.output_names() for hbn in self.hbns]
        for dic in dics:
            for key, vals in dic.items():
                [dd[key].add(val) for val in vals]
        return dd

    def get_perlnd_data(self,constituent,t_code = 'yearly'):
        t_cons = ch.get_tcons2(constituent,'PERLND')
        
        df = pd.concat([self.get_multiple_timeseries(t_opn = 'PERLND',
                                     t_code = t_code,
                                     t_con = t_con,
                                     opnids = None)
                         for t_con in t_cons],axis = 0)
        
        return df
         
         
    def get_rchres_data(self,constituent,reach_ids,units = 'mg/l',t_code = 'daily'):
        '''
        Convience function for accessing the hbn time series associated with our current
        calibration method. Assumes you are summing across all dataframes.

        Parameters
        ----------
        hbn : TYPE
            DESCRIPTION.
        nutrient_id : TYPE
            DESCRIPTION.
        reach_ids : TYPE
            DESCRIPTION.
        flux : TYPE, optional
            DESCRIPTION. The default is None.

        Returns
        -------
        df : TYPE
            DESCRIPTION.

        '''
        
        
        
        t_cons = ch.get_tcons2(constituent,'RCHRES',units)
        

        
        df = pd.concat([self.get_multiple_timeseries(t_opn = 'RCHRES',
                                     t_code =t_code,
                                     t_con = t_con,
                                     opnids = reach_ids)
                         for t_con in t_cons],axis = 1).sum(1).to_frame()
        
        if (constituent == 'Q') & (units == 'cfs'):            
            df = df/CF2CFS[t_code]*43560 #Acrfeet/invl to cubic feet/s
            
        df.attrs['unit'] = units
        df.attrs['constituent'] = constituent
        df.attrs['reach_ids'] = reach_ids
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
    def __init__(self,file_name,Map = True):
        self.data(file_name,Map)
        self.tcodes = {'minutely':1,'hourly':2,'daily':3,'monthly':4,'yearly':5, 
                       1:'minutely',2:'hourly',3:'daily',4:'monthly',5:'yearly',
                       'min':1,'h':2,'D':3,'M':4,'Y':5,'H':2,'ME':4,'YE':5}
        self.pandas_tcodes = {1:'min',2:'h',3:'D',4:'ME',5:'YE'}
    def data(self,file_name,Map = False):
        self.file_name = file_name
        self.data = fromfile(self.file_name, 'B')
        if self.data[0] != 0xFD:
            print('BAD HBN FILE - must start with magic number 0xFD')
            return
        if Map == True:
            self.map_hbn()
        else:
            self._clear_cache()
    
    def map_hbn(self):
        """
        Reads ALL data from hbn_file and return them in DataFrame
        Parameters
        ----------
        hbn_file : str
            Name/path of HBN created by HSPF.
        Returns
        -------
        df_summary : DataFrame
            Summary information of data found in HBN file (also saved to HDF5 file.)
        """
        
        self.simulation_duration_count = 0
        self.data_frames = {}
        self.summary = []
        self.summarycols = ['Operation', 'Activity', 'segment', 'Frequency', 'Shape', 'Start', 'Stop']
        self.summaryindx = []
        self.output_dictionary = {}
        
        data = self.data

        # Build layout maps of the file's contents
        mapn = defaultdict(list)
        mapd = defaultdict(list)
        index = 1  # already used first byte (magic number)
        while index < len(data):
            rc1, rc2, rc3, rc, rectype, operation, id, activity = unpack('4BI8sI8s', data[index:index + 28])
            rc1 = int(rc1 >> 2)
            rc2 = int(rc2) * 64 + rc1  # 2**6
            rc3 = int(rc3) * 16384 + rc2  # 2**14
            reclen = int(rc) * 4194304 + rc3 - 24  # 2**22

            operation = operation.decode('ascii').strip()  # Python3 converts to bytearray not string
            activity = activity.decode('ascii').strip()

            if operation not in {'PERLND', 'IMPLND', 'RCHRES'}:
                print('ALIGNMENT ERROR', operation)

            if rectype == 1:  # data record
                tcode = unpack('I', data[index + 32: index + 36])[0]
                mapd[operation, id, activity, tcode].append((index, reclen))
            elif rectype == 0:  # data names record
                i = index + 28
                slen = 0
                while slen < reclen:
                    ln = unpack('I', data[i + slen: i + slen + 4])[0]
                    n = unpack(f'{ln}s', data[i + slen + 4: i + slen + 4 + ln])[0].decode('ascii').strip()
                    mapn[operation, id, activity].append(n.replace('-', ''))
                    slen += 4 + ln
            else:
                print('UNKNOW RECTYPE', rectype)
            if reclen < 36:
                index += reclen + 29  # found by trial and error
            else:
                index += reclen + 30
        self.mapn = dict(mapn)
        self.mapd = dict(mapd)

    
    def read_data(self,operation,id,activity,tcode):
        rows = []
        times = []
        nvals = len(self.mapn[operation, id, activity]) # number constituent timeseries
        utc_offset = timezone(timedelta(hours=-6)) #UTC is 6hours ahead of CST
        for (index, reclen) in self.mapd[operation, id, activity, tcode]:
            yr, mo, dy, hr, mn = unpack('5I', self.data[index + 36: index + 56])
            hr = hr-1
            dt = datetime(yr, mo, dy, 0, mn ,tzinfo=utc_offset) + timedelta(hours=hr)
            times.append(dt)

            index += 56
            row = unpack(f'{nvals}f', self.data[index:index + (4 * nvals)])
            rows.append(row)
        dfname = f'{operation}_{activity}_{id:03d}_{tcode}'
        if self.simulation_duration_count == 0:
            self.simulation_duration_count = len(times)
        df = DataFrame(rows, index=times, columns=self.mapn[operation, id, activity]).sort_index(level = 'index')
        if len(df) > 0:
            #if tcode in ['daily',3]:
            self.summaryindx.append(dfname)
            self.summary.append((operation, activity, str(id), self.tcodes[tcode], str(df.shape), df.index[0], df.index[-1]))
            self.output_dictionary[dfname] = self.mapn[operation, id, activity]
            self.data_frames[dfname] = df.resample(self.pandas_tcodes[tcode]).mean() # sets the hours to 00 for non hourly time steps # an expensive operation probably
            return self.data_frames[dfname]
        else:
            return None
    
    def _clear_cache(self):
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
            return print('No Constituent-OPNID relationship found')
        return result
    
    
    def infer_activity(self,t_opn, t_cons):  
        result = [k[-1] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn)]
        if len(result) == 0:
            return print('No Constituent-Activity relationship found')
        assert(len(set(result)) == 1)
        return result[0]
    
    
    def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
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
            if activity is None:
                return None
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
            df = None
            
        return df
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
        # a single constituent but multiple opnids
        if isinstance(t_code,str):
            t_code = self.tcodes[t_code]
            
        if activity is None:
            activity = self.infer_activity(t_opn,t_con)
            if activity is None:
                return None
           
        if opnids is None:
            opnids = self.infer_opnids(t_opn,t_con,activity)
            if opnids is None:
                return None 
           
        df = None
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
    
    @staticmethod          
    def get_perlands(summary_indxs):
         perlands =  [int(summary_indx.split('_')[-2]) for summary_indx in summary_indxs]
         return perlands
     
 
# Helper functions for linking hbn file and nutrient ids    
def get_perlnd_data(hbn,nutrient_id,flux = None):
    t_cons = ch.get_tcons(nutrient_id,'PERLND')
 
    df = pd.concat([hbn.get_multiple_timeseries(t_opn = 'PERLND',
                                 t_code = 'yearly',
                                 t_con = t_con,
                                 opnids = None)
                     for t_con in t_cons],axis = 0)
    
    return df
     
     
def get_rchres_data(hbn,nutrient_id,reach_ids,method = 'Load'):
    '''
    Convience function for accessing the hbn time series associated with our current
    calibration method. Assumes you are summing across all dataframes.

    Parameters
    ----------
    hbn : TYPE
        DESCRIPTION.
    nutrient_id : TYPE
        DESCRIPTION.
    reach_ids : TYPE
        DESCRIPTION.
    flux : TYPE, optional
        DESCRIPTION. The default is None.

    Returns
    -------
    df : TYPE
        DESCRIPTION.

    '''
    opnids = reach_ids # list of integer values
    t_cons = ch.get_tcons(nutrient_id,'RCHRES',method)
    
    
    df = pd.concat([hbn.get_multiple_timeseries(t_opn = 'RCHRES',
                                 t_code = 'daily',
                                 t_con = t_con,
                                 opnids = opnids)
                     for t_con in t_cons],axis = 1).sum(1).to_frame()
    

    return df

    
    
    
# -*- coding: utf-8 -*-
"""
Read and query HSPF binary output (HBN) files.

This module provides classes and helper functions for reading HSPF
(Hydrological Simulation Program – Fortran) binary output files (``.hbn``).
The two main entry-points are :class:`hbnClass`, which wraps a single HBN
file, and :class:`hbnInterface`, which aggregates several :class:`hbnClass`
instances so that time-series queries can span multiple output files.

Module-level convenience functions retrieve simulated flow, water
temperature, and water-quality constituents from HBN data, converting
units where necessary.

Module-level Constants
----------------------
CF2CFS : dict
    Conversion factors from cubic-feet per interval to cubic-feet per
    second, keyed by frequency string, pandas offset alias, or HSPF
    time-code integer.
AGG_DEFAULTS : dict
    Default aggregation method (``'mean'`` or ``'sum'``) for each unit
    string.
UNIT_DEFAULTS : dict
    Default display unit for each constituent abbreviation.
LOSS_MAP : dict
    Mapping of constituent abbreviation to ``(inflow_names, outflow_names)``
    tuples used by :meth:`hbnInterface.reach_losses`.
TCODES2FREQ : dict
    HSPF numeric time-codes (1–5) mapped to pandas frequency aliases.
"""
from hspf import helpers
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

# Seconds per interval – used to convert cubic-feet/interval to cfs.
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

# Default aggregation method for each unit (mean or sum).
AGG_DEFAULTS = {'cfs':'mean',
                'mg/l':'mean',
                'degF': 'mean',
                'lb':'sum'}

# Default display unit for each constituent abbreviation.
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
    """Retrieve a summed impervious-land constituent time-series from an HBN source.

    Looks up the required HBN constituent names for the given
    high-level constituent, retrieves each time-series from *hbn*,
    and returns their sum.  TSS values are converted from tons to
    pounds (×2000).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source that implements ``get_multiple_timeseries``.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TSS'``, ``'TP'``).
    time_step : int or str
        HSPF time-code or frequency string for the desired output
        interval.

    Returns
    -------
    pandas.DataFrame
        Summed constituent time-series across all IMPLND segments.
    """
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
    """Retrieve a summed pervious-land constituent time-series from an HBN source.

    Analogous to :func:`get_simulated_implnd_constituent` but queries
    ``PERLND`` operations.  TSS values are converted from tons to
    pounds (×2000).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source that implements ``get_multiple_timeseries``.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TSS'``, ``'TP'``).
    time_step : int or str
        HSPF time-code or frequency string for the desired output
        interval.

    Returns
    -------
    pandas.DataFrame
        Summed constituent time-series across all PERLND segments.
    """
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
    """Retrieve per-acre constituent loads for all pervious and impervious lands.

    Combines PERLND and IMPLND outputs into a single long-format
    DataFrame with columns for datetime, operation ID, constituent
    value, operation type, and units.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    constituent : str
        High-level constituent abbreviation.
    catchment_ids : list of int, optional
        Reserved for future filtering; currently unused.
    time_step : int or str, optional
        HSPF time-code or frequency string (default ``5`` = yearly).

    Returns
    -------
    pandas.DataFrame
        Long-format DataFrame with columns ``'datetime'``,
        ``'OPNID'``, *constituent*, ``'OPERATION'``, and ``'unit'``.
    """
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
    """Retrieve simulated streamflow from one or more RCHRES segments.

    Reads the ``ROVOL`` time-series (acre-ft per interval) and converts
    to the requested *unit*.  Negative reach IDs cause the
    corresponding flow to be subtracted (e.g. for split-flow routing).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Reach segment IDs.  A negative ID means its flow is subtracted.
    unit : {'cfs', 'acrft'}, optional
        Desired output unit (default ``'cfs'``).

    Returns
    -------
    pandas.Series
        Flow time-series with ``attrs['unit']`` set to *unit*.
    """
    
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
    """Retrieve simulated water temperature for a single reach.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Must contain exactly one reach ID.

    Returns
    -------
    pandas.Series
        Water-temperature time-series with ``attrs['unit']`` set to
        ``'degf'``.

    Raises
    ------
    AssertionError
        If *reach_ids* contains more than one element.
    """
    assert len(reach_ids) == 1, "Temperature can only be retreived for one reach at a time."


    wt = hbn.get_multiple_timeseries('RCHRES',time_step,'TW', reach_ids)
    wt = wt.sum(axis=1)
    wt.attrs['unit'] = 'degf'
    
    return wt
    

def get_simulated_reach_constituent(hbn,constituent,time_step,reach_ids,unit = None):
    """Retrieve a simulated reach water-quality constituent.

    Fetches the raw load (lb) time-series for *constituent*, optionally
    converts to concentration (mg/L) using simulated flow, and applies
    sign corrections for negative reach IDs.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TP'``, ``'TSS'``).
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Reach segment IDs.  Negative IDs are subtracted.
    unit : {'mg/l', 'lb'}, optional
        Desired output unit.  Defaults to the value in
        :data:`UNIT_DEFAULTS` for *constituent*.

    Returns
    -------
    pandas.Series
        Constituent time-series with ``attrs`` for ``'unit'``,
        ``'constituent'``, and ``'reach_ids'``.
    """
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
    """Aggregate interface over multiple HBN files.

    Wraps a list of :class:`hbnClass` instances so that time-series
    queries are transparently concatenated across files.  This is useful
    when a single HSPF simulation produces several ``.hbn`` outputs
    (e.g. one per sub-basin).

    Parameters
    ----------
    file_paths : list of str or pathlib.Path
        Paths to the HBN files.
    Map : bool, optional
        If ``True`` (default), each file is mapped on construction.

    Attributes
    ----------
    names : list
        Original file paths.
    hbns : list of hbnClass
        Individual HBN readers.
    """

    def __init__(self,file_paths,Map = True):
        self.names = [file_path for file_path in file_paths]
        self.hbns = [hbnClass(file_path,Map) for file_path in file_paths]
        
    def _clear_cache(self):
        """Clear cached DataFrames in every underlying :class:`hbnClass`."""
        [hbn._clear_cache() for hbn in self.hbns]
        

        
    def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        """Retrieve a single constituent time-series concatenated across files.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_cons : str
            Constituent name stored in the HBN file.
        t_code : int or str
            HSPF time-code or frequency string.
        opnid : int
            Operation segment ID.
        activity : str, optional
            HSPF activity name (e.g. ``'HYDR'``).  Inferred when
            ``None``.

        Returns
        -------
        pandas.DataFrame
            Time-series concatenated column-wise from each HBN file.

        Raises
        ------
        ValueError
            If no data is found for the given query parameters.
        """
        df = pd.concat([hbn._get_time_series(t_opn, t_cons, t_code, opnid, activity) for hbn in self.hbns],axis = 1)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
        
        if long_format:
            df = df.reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID',value_name = t_con)
            df.rename(columns = {'index':'datetime'},inplace = True)
            df['OPERATION'] = t_opn
        return df
        
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None,axis = 1,long_format = False):
        """Retrieve a constituent across multiple segments, concatenated across files.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_code : int or str
            HSPF time-code or frequency string.
        t_con : str
            Constituent name stored in the HBN file.
        opnids : list of int, optional
            Segment IDs to include.  If ``None``, all available IDs are
            used.
        activity : str, optional
            HSPF activity name.  Inferred when ``None``.
        axis : int, optional
            Concatenation axis (default ``1``).
        long_format : bool, optional
            If ``True``, melt the result into long format with columns
            ``'OPNID'``, ``'value'``, ``'TIMESERIES'``, and
            ``'OPERATION'``.

        Returns
        -------
        pandas.DataFrame
            Wide or long-format DataFrame of the requested time-series.

        Raises
        ------
        ValueError
            If no data is found for the given query parameters.
        """
        df = pd.concat([hbn._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity) for hbn in self.hbns],axis = 1)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
        
        if long_format:
            df = df.reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID',value_name = 'value')
            df.rename(columns = {'index':'datetime'},inplace = True)
            df['TIMESERIES'] = t_con
            df['OPERATION'] = t_opn
        return df

    def get_perlnd_constituent(self,constituent,perlnd_ids = None,time_step = 5):
        """Retrieve a summed pervious-land constituent time-series.

        Parameters
        ----------
        constituent : str
            High-level constituent abbreviation.
        perlnd_ids : list of int, optional
            Reserved; currently unused.
        time_step : int or str, optional
            HSPF time-code (default ``5`` = yearly).

        Returns
        -------
        pandas.DataFrame
            Summed constituent time-series across PERLND segments.
        """
        return get_simulated_perlnd_constituent(self,constituent,time_step)

    def get_implnd_constituent(self,constituent,implnd_ids = None,time_step = 5):
        """Retrieve a summed impervious-land constituent time-series.

        Parameters
        ----------
        constituent : str
            High-level constituent abbreviation.
        implnd_ids : list of int, optional
            Reserved; currently unused.
        time_step : int or str, optional
            HSPF time-code (default ``5`` = yearly).

        Returns
        -------
        pandas.DataFrame
            Summed constituent time-series across IMPLND segments.
        """
        return get_simulated_implnd_constituent(self,constituent,time_step)

        
    def get_reach_constituent(self,constituent,reach_ids,time_step,unit = None):
        """Retrieve a reach constituent, dispatching to flow or temperature helpers.

        Parameters
        ----------
        constituent : str
            ``'Q'`` for flow, ``'WT'`` for water temperature, or any
            water-quality constituent abbreviation.
        reach_ids : list of int
            Reach segment IDs.
        time_step : int or str
            HSPF time-code or frequency string.
        unit : str, optional
            Desired output unit (passed through to the underlying
            retrieval function).

        Returns
        -------
        pandas.DataFrame
            Single-column DataFrame of the requested constituent.
        """
        if constituent == 'Q':
            df = get_simulated_flow(self,time_step,reach_ids,unit = unit)
        elif constituent == 'WT':
            df = get_simulated_temperature(self,time_step,reach_ids)
        else:     
            df = get_simulated_reach_constituent(self,constituent,time_step,reach_ids,unit)
        return df.to_frame()
    
    def output_names(self):
        """Return available output names merged across all HBN files.

        Returns
        -------
        dict
            Nested dictionary ``{operation: {activity: set_of_names}}``.
        """
        dics =  [hbn.output_names() for hbn in self.hbns]
        return merge_dicts(dics)
        # for dic in dics:
        #     for operation, vals in dic.items():
        #         for activity,v in vals.items():
        #             [dd[operation][activity].add(t) for t in v]
        # return dd

    def _timeseries(self):
        """Build a flat list of time-series descriptors from the merged map.

        Returns
        -------
        list of list
            Each inner list is ``[operation, id, activity, name]``.
        """
        mapn = self._mapn()
        timeseries = []
        for key, vals in mapn.items():
            _key = list(key)
            for val in vals:
                timeseries.append(_key + [val])
        return timeseries      
            

    def _mapn(self):
        """Merge constituent-name maps from all underlying HBN files.

        Returns
        -------
        collections.defaultdict
            Mapping of ``(operation, id, activity)`` to a set of
            constituent names.
        """
        dd = defaultdict(set)    
        dics =  [hbn.mapn for hbn in self.hbns]
        for dic in dics:
            for key, vals in dic.items():
                [dd[key].add(val) for val in vals]
        return dd 
    
    def get_perlnd_data(self,constituent,t_code = 'yearly'):
        """Retrieve all PERLND time-series for a constituent.

        Parameters
        ----------
        constituent : str
            High-level constituent abbreviation.
        t_code : int or str, optional
            HSPF time-code or frequency string (default ``'yearly'``).

        Returns
        -------
        pandas.DataFrame
            Concatenated time-series for the constituent's underlying
            HBN names across all PERLND segments.
        """
        t_cons = helpers.get_tcons(constituent,'PERLND')
        
        df = pd.concat([self.get_multiple_timeseries(t_opn = 'PERLND',
                                     t_code = t_code,
                                     t_con = t_con,
                                     opnids = None)
                         for t_con in t_cons],axis = 0)
        
        return df
         
          
    def get_rchres_output(self,constituent,units = 'mg/l',t_code = 5):
        """Retrieve a summed RCHRES constituent used for calibration.

        Convenience method that sums the underlying HBN time-series
        names for *constituent* across all reach segments.

        Parameters
        ----------
        constituent : str
            High-level constituent abbreviation.
        units : str, optional
            Unit label attached to the result (default ``'mg/l'``).
        t_code : int or str, optional
            HSPF time-code (default ``5`` = yearly).

        Returns
        -------
        pandas.DataFrame
            Summed time-series with ``attrs`` for ``'unit'`` and
            ``'constituent'``.
        """
        t_cons = helpers.get_tcons(constituent,'RCHRES',units)
        df = sum([self.get_multiple_timeseries('RCHRES',t_code,t_con) for t_con in t_cons])
        df.attrs['unit'] = units
        df.attrs['constituent'] = constituent
        return df
    
        
    def reach_losses(self,constituent,t_code): 
        """Compute the inflow-to-outflow ratio for a reach constituent.

        Parameters
        ----------
        constituent : str
            Constituent key present in :data:`LOSS_MAP`.
        t_code : int or str
            HSPF time-code or frequency string.

        Returns
        -------
        pandas.Series
            Ratio of total inflow to total outflow for each reach.
        """
        inflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][0]],axis=1).sum()
        outflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][1]],axis=1).sum()
        return inflows/outflows
        
# Inflow/outflow constituent names used to compute reach losses.
LOSS_MAP = {'Q':(['IVOL'],['ROVOL']),
       'TSS': (['ISEDTOT'],['ROSEDTOT']),
       'TP': (['PTOTIN'],['PTOTOUT']),
       'N': ([ 'NO2INTOT', 'NO3INTOT'],['NO3OUTTOT','NO2OUTTOT']),
       'TKN':(['TAMINTOT','NTOTORGIN'],['TAMOUTTOT','NTOTORGOUT']),
       'OP': (['PO4INDIS'],['PO4OUTDIS'])}
# HSPF numeric time-codes mapped to pandas frequency aliases.
TCODES2FREQ = {1:'min',2:'h',3:'D',4:'M',5:'Y'}
    
class hbnClass:
    """Reader for a single HSPF binary output (HBN) file.

    Parses the binary record layout of the ``.hbn`` file, builds an
    in-memory index of constituent names (``mapn``) and data-record
    positions (``mapd``), and lazily reads time-series data on demand.

    Parameters
    ----------
    file_name : str or pathlib.Path
        Path to the ``.hbn`` file.
    Map : bool, optional
        If ``True`` (default), the file is fully mapped on construction
        via :meth:`map_hbn`.

    Attributes
    ----------
    file_name : str or pathlib.Path
        Path to the underlying binary file.
    data : numpy.ndarray
        Raw byte array of the file contents.
    mapn : dict
        ``{(operation, id, activity): [name, ...]}`` constituent-name
        map.
    mapd : dict
        ``{(operation, id, activity, tcode): [(index, reclen), ...]}``
        data-record position map.
    data_frames : dict
        Cache of already-read :class:`pandas.DataFrame` objects keyed
        by summary index strings.
    tcodes : dict
        Bidirectional mapping between time-code integers and frequency
        strings.
    pandas_tcodes : dict
        Time-code integers mapped to pandas offset aliases.
    """

    def __init__(self,file_name,Map = True):
        self.data(file_name,Map)
        self.tcodes = {'minutely':1,'hourly':2,'daily':3,'monthly':4,'yearly':5, 
                       1:'minutely',2:'hourly',3:'daily',4:'monthly',5:'yearly',
                       'min':1,'h':2,'D':3,'M':4,'Y':5,'H':2,'ME':4,'YE':5}
        self.pandas_tcodes = {1:'min',2:'h',3:'D',4:'ME',5:'YE'}
    def data(self,file_name,Map = False):
        """Load raw bytes from an HBN file and optionally map its contents.

        Parameters
        ----------
        file_name : str or pathlib.Path
            Path to the ``.hbn`` file.
        Map : bool, optional
            If ``True``, call :meth:`map_hbn` after loading
            (default ``False``).
        """
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
        """Parse the full HBN file and build name/data position maps.

        Iterates through every binary record in :attr:`data`, populating
        :attr:`mapn` (constituent names per operation/segment/activity)
        and :attr:`mapd` (byte offsets of data records).  Also
        initialises the summary and cache structures.

        Returns
        -------
        None
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
        """Read and cache a single time-series DataFrame from the binary data.

        Unpacks the raw bytes at the offsets stored in :attr:`mapd` and
        builds a :class:`pandas.DataFrame` indexed by datetime.  The
        result is resampled to regularise the time index and cached in
        :attr:`data_frames`.

        Parameters
        ----------
        operation : str
            ``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``.
        id : int
            Operation segment ID.
        activity : str
            HSPF activity name (e.g. ``'HYDR'``).
        tcode : int
            HSPF numeric time-code (1–5).

        Returns
        -------
        pandas.DataFrame or None
            The resampled DataFrame, or ``None`` if no rows were found.
        """
        rows = []
        times = []
        nvals = len(self.mapn[operation, id, activity]) # number constituent timeseries
        #utc_offset = timezone(timedelta(hours=-6)) #UTC is 6hours ahead of CST
        for (index, reclen) in self.mapd[operation, id, activity, tcode]:
            yr, mo, dy, hr, mn = unpack('5I', self.data[index + 36: index + 56])
            hr = hr-1
            #dt = datetime(yr, mo, dy, 0, mn ,tzinfo=utc_offset) + timedelta(hours=hr)
            dt = datetime(yr, mo, dy, 0, mn ) + timedelta(hours=hr)

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
        """Reset all cached DataFrames and summary structures."""
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
        """Infer operation segment IDs that contain a given constituent.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_cons : str
            Constituent name to search for.
        activity : str
            HSPF activity name.

        Returns
        -------
        list of int
            Matching segment IDs, or ``[-1]`` if none are found.
        """
        result = [k[-2] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn) & (k[-1] == activity)]
        if len(result) == 0:
            result = [-1]
        #     return print('No Constituent-OPNID relationship found')
        return result
    
    
    def infer_activity(self,t_opn, t_cons):  
        """Infer the HSPF activity that contains a given constituent.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_cons : str
            Constituent name to search for.

        Returns
        -------
        str
            The unique activity name, or an empty string if the
            constituent is not found.

        Raises
        ------
        AssertionError
            If the constituent is found under more than one activity.
        """
        result = [k[-1] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn)]
        if len(result) == 0:
            result = ''
        else:#     return print('No Constituent-Activity relationship found')
            assert(len(set(result)) == 1)
            result = result[0]
        return result
    
    def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        """Retrieve a single constituent time-series, raising on empty results.

        Thin wrapper around :meth:`_get_time_series` that raises
        :class:`ValueError` when no data is found.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_cons : str
            Constituent name.
        t_code : int or str
            HSPF time-code or frequency string.
        opnid : int
            Operation segment ID.
        activity : str, optional
            HSPF activity name.  Inferred when ``None``.

        Returns
        -------
        pandas.Series
            The requested time-series.

        Raises
        ------
        ValueError
            If the underlying query returns an empty DataFrame.
        """
        df = self._get_time_series(t_opn, t_cons, t_code, opnid, activity)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
        return df

    def _get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
        """Retrieve a single constituent time-series from the HBN file.

        Looks up or reads the requested record, extracts the column for
        *t_cons*, and filters to dates on or after 1996-01-01.

        Parameters
        ----------
        t_opn : str
            Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        t_cons : str
            Constituent name.
        t_code : int or str
            HSPF time-code or frequency string.
        opnid : int
            Operation segment ID.
        activity : str, optional
            HSPF activity name.  Inferred when ``None``.

        Returns
        -------
        pandas.Series or pandas.DataFrame
            The time-series for *t_cons*, or an empty DataFrame if the
            record is not present.
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
        
        df.index.name = 'datetime'
        return df
    
    def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
        """Retrieve a constituent across multiple segments, raising on empty results.

        Thin wrapper around :meth:`_get_multiple_timeseries` that
        raises :class:`ValueError` when no data is found.

        Parameters
        ----------
        t_opn : str
            Operation type.
        t_code : int or str
            HSPF time-code or frequency string.
        t_con : str
            Constituent name.
        opnids : list of int, optional
            Segment IDs.  If ``None``, inferred from :attr:`mapn`.
        activity : str, optional
            HSPF activity name.  Inferred when ``None``.

        Returns
        -------
        pandas.DataFrame
            Wide-format DataFrame with one column per segment.

        Raises
        ------
        ValueError
            If the underlying query returns an empty DataFrame.
        """
        df = self._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity)
        if df.empty:
            raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
        return df
    
    def _get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
        """Retrieve a single constituent for multiple segments.

        Parameters
        ----------
        t_opn : str
            Operation type.
        t_code : int or str
            HSPF time-code or frequency string.
        t_con : str
            Constituent name.
        opnids : list of int, optional
            Segment IDs.  If ``None``, inferred from :attr:`mapn`.
        activity : str, optional
            HSPF activity name.  Inferred when ``None``.

        Returns
        -------
        pandas.DataFrame
            Wide-format DataFrame with one column per segment, or an
            empty DataFrame if no matching records exist.
        """

        
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
        """Return constituent names grouped by activity.

        .. note::

           This definition is overridden by the subsequent
           :meth:`output_names` which groups by operation *and*
           activity.

        Returns
        -------
        dict
            ``{activity: set_of_names}``.
        """
        activities = set([k[-1] for k,v in self.mapn.items()])
        dic = {}
        for activity in activities:
            t_cons = [v for k,v in self.mapn.items() if k[-1] == activity]   
            dic[activity] = set([item for sublist in t_cons for item in sublist])
        return dic
    

    def output_names(self):
        """Return constituent names grouped by operation and activity.

        This definition supersedes the earlier :meth:`output_names`
        that groups only by activity.

        Returns
        -------
        dict
            Nested dictionary
            ``{operation: {activity: set_of_names}}``.
        """

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
        """Build a flat list of time-series descriptors from :attr:`mapn`.

        Returns
        -------
        list of list
            Each inner list is ``[operation, id, activity, name]``.
        """
        mapn = self.mapn
        timeseries = []
        for key, vals in mapn.items():
            _key = list(key)
            for val in vals:
                timeseries.append(_key + [val])
        return timeseries      

    @staticmethod          
    def get_perlands(summary_indxs):
         """Extract PERLND segment IDs from summary index strings.

         Parameters
         ----------
         summary_indxs : list of str
             Summary index strings in the format
             ``'<OPN>_<ACTIVITY>_<ID>_<TCODE>'``.

         Returns
         -------
         list of int
             Extracted integer segment IDs.
         """
         perlands =  [int(summary_indx.split('_')[-2]) for summary_indx in summary_indxs]
         return perlands
     

def merge_dicts(dicts):
    """Merge a list of dictionaries, combining sets at the leaf level.

    Recursively walks each dictionary.  When both sides have a
    ``dict`` for the same key the merge recurses; when both sides
    have a ``set`` the sets are unioned.  Incompatible types for the
    same key raise :class:`ValueError`.

    Parameters
    ----------
    dicts : list of dict
        Dictionaries to merge.

    Returns
    -------
    dict
        The merged dictionary.

    Raises
    ------
    ValueError
        If the same key maps to incompatible types across
        dictionaries.
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
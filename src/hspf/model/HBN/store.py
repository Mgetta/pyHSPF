
from dataclasses import dataclass
from collections import defaultdict
import pandas as pd
from pathlib import Path

from .reader import HbnFile, HbnRecord, HbnRecordKey
from hspf.core.types import EntityType, Activity, OutputLevel, EntityRef, Block

#named tuple


from collections import namedtuple

@dataclass
class RecordLocation:
    hbn_file: HbnFile
    record: HbnRecord

    def decode(self) -> pd.DataFrame:
        return self.hbn_file.decode(self.record)

class HbnStore:
    """Aggregate interface over multiple HBN files.

    Wraps a list of :class:`HbnFile` instances so that time-series
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
    file_paths : list
        Original file paths.
    names : list
        Base names (stem) of the HBN files.
    hbns : list of HbnFile
        Individual HBN readers.
    """

    def __init__(self,file_paths):
        self.file_paths = [Path(file_path) for file_path in file_paths]
        self.names = [file_path.stem for file_path in file_paths]
        self.files = [HbnFile(file_path) for file_path in file_paths]

        self._records = self._get_records()
        self._cache: dict[HbnRecordKey, pd.DataFrame] = {}


    def _get_records(self):
        records = {}
        for _, hbn_file in enumerate(self.files):
            for key, record in hbn_file.scan().items():
                if key in records:
                    raise ValueError(f"Duplicate HBN record for {key}")
                records[key] = RecordLocation(hbn_file, record)
        return records

    def _decoded(self, record_key: HbnRecordKey) -> pd.DataFrame:
        if record_key not in self._cache:
            self._cache[record_key] = self._records[record_key].decode()
        cached = self._cache[record_key]
        return cached
    
    def infer_opnids(self,t_opn, t_cons,activity,tcode = 5):
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
        tcode : int, optional
            The time code to filter by (default is 5).
        """
        result = []
        operation = EntityType(t_opn)
        activity = Activity(activity)
        output_level = OutputLevel(tcode)

        for record_key, record_location in self._records.items():
            if (t_cons in record_location.record.columns) & (record_key.entity.entity_type == operation) & (record_key.activity == activity) & (record_key.output_level == output_level):
                result.append(record_key.entity)
        if result:
            return result
        else:
            raise ValueError(f"No matching operation segment IDs found for operation '{t_opn}', constituent '{t_cons}', and activity '{activity}'")
    
    
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

    
    def output_dictionary(self):
        """Retrieve the output dictionary from all underlying HBN files.

        Returns
        -------
        dict
            Combined output dictionary from each HBN file.
        """
        output_dicts = [hbn.output_dictionary for hbn in self.hbns]
        combined_dict = {}
        for d in output_dicts:
            combined_dict.update(d)
        return combined_dict

    def mapd(self):
        """Map all underlying HBN files.

        Returns
        -------
        dictionary of mmap.mmap
            Memory-mapped file objects for each HBN file.
        """
        # merge the dictionaries from each hbnClass into a single dictionary
        merged_dict = {}
        for hbn in self.hbns:
            merged_dict |= hbn.mapd
        return merged_dict
    
    def record(self, operation, opnid, activity, tcode):
        """Read the output for a specific operation, opnid, activity, and tcode from all HBN files and concatenate.

        Parameters
        ----------
        operation : str
            HSPF operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        opnid : int
            Operation segment ID.
        activity : str
            HSPF activity name (e.g. ``'HYDR'``).  Inferred when ``None``.
        tcode : int or str
            HSPF time-code or frequency string.

        Returns
        -------
        pandas.DataFrame
            Output data concatenated from each HBN file.

        Raises
        ------
        ValueError
            If no data is found for the given query parameters.
        """
        record_key = HbnRecordKey(
            entity=EntityRef(operation, opnid),
            activity=Activity(activity),
            output_level=OutputLevel(tcode),
        )
        return self._decoded(record_key)

    def series(self, operation, opnid, activity, tcode, constituent):
        """Read the time series for a specific operation, opnid, activity, tcode, and constituent from all HBN files and concatenate.

        Parameters
        ----------
        operation : str
            HSPF operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
        opnid : int
            Operation segment ID.
        activity : str
            HSPF activity name (e.g. ``'HYDR'``).  Inferred when ``None``.
        tcode : int or str
            HSPF time-code or frequency string.
        constituent : str
            Name of the constituent to retrieve.

        Returns
        -------
        pandas.Series
            Time series data concatenated from each HBN file.

        Raises
        ------
        ValueError
            If no data is found for the given query parameters.
        """
        
        return self.record(operation, opnid, activity, tcode)[constituent]
    
#     def get_block(self, operation, activity, tcode):
#         """Read a single HBN block from all files and concatenate.

#         Parameters
#         ----------
#         operation : str
#             HSPF operation type (``'PERLND'``, ``'IMPLND'``, or
#             ``'RCHRES'``).

#         activity : str
#             HSPF activity name (e.g. ``'HYDR'``).  Inferred when ``None``.
#         tcode : int or str
#             HSPF time-code or frequency string.

#         Returns
#         -------
#         pandas.DataFrame
#             Block of data concatenated from each HBN file.

#         Raises
#         ------
#         ValueError
#             If no data is found for the given query parameters.
#         """
#         df_list = [hbn.get_block(operation, activity, tcode) for hbn in self.hbns]
#         df = pd.concat(df_list, axis=0)
#         if df.empty:
#             raise ValueError(f"No data found for {operation} {activity} {tcode}")
#         return df

#     def iter_blocks(self):
#         """Retrieve all unique blocks across the HBN files.

#         Returns
#         -------
#         set of tuples
#             Each tuple contains (operation, activity, tcode) representing a unique block.
#         """
        
#         blocks = [(operation, activity, int(tcode)) for operation, _, activity, tcode  in self.mapd().keys()]
#         return set(blocks)
    
#     def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
#         """Retrieve a single constituent time-series concatenated across files.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_cons : str
#             Constituent name stored in the HBN file.
#         t_code : int or str
#             HSPF time-code or frequency string.
#         opnid : int
#             Operation segment ID.
#         activity : str, optional
#             HSPF activity name (e.g. ``'HYDR'``).  Inferred when
#             ``None``.

#         Returns
#         -------
#         pandas.DataFrame
#             Time-series concatenated column-wise from each HBN file.

#         Raises
#         ------
#         ValueError
#             If no data is found for the given query parameters.
#         """
#         df = pd.concat([hbn._get_time_series(t_opn, t_cons, t_code, opnid, activity) for hbn in self.hbns],axis = 1)
#         if df.empty:
#             raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
        
#         if long_format:
#             df = df.reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID',value_name = t_con)
#             df.rename(columns = {'index':'datetime'},inplace = True)
#             df['OPERATION'] = t_opn
#         return df
        
#     def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None,axis = 1,long_format = False):
#         """Retrieve a constituent across multiple segments, concatenated across files.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_code : int or str
#             HSPF time-code or frequency string.
#         t_con : str
#             Constituent name stored in the HBN file.
#         opnids : list of int, optional
#             Segment IDs to include.  If ``None``, all available IDs are
#             used.
#         activity : str, optional
#             HSPF activity name.  Inferred when ``None``.
#         axis : int, optional
#             Concatenation axis (default ``1``).
#         long_format : bool, optional
#             If ``True``, melt the result into long format with columns
#             ``'OPNID'``, ``'value'``, ``'TIMESERIES'``, and
#             ``'OPERATION'``.

#         Returns
#         -------
#         pandas.DataFrame
#             Wide or long-format DataFrame of the requested time-series.

#         Raises
#         ------
#         ValueError
#             If no data is found for the given query parameters.
#         """
#         df = pd.concat([hbn._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity) for hbn in self.hbns],axis = 1)
#         if df.empty:
#             raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
        
#         if long_format:
#             df = df.reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID',value_name = 'value')
#             df.rename(columns = {'index':'datetime'},inplace = True)
#             df['TIMESERIES'] = t_con
#             df['OPERATION'] = t_opn
#         return df

#     def get_perlnd_constituent(self,constituent,perlnd_ids = None,time_step = 5):
#         """Retrieve a summed pervious-land constituent time-series.

#         Parameters
#         ----------
#         constituent : str
#             High-level constituent abbreviation.
#         perlnd_ids : list of int, optional
#             Reserved; currently unused.
#         time_step : int or str, optional
#             HSPF time-code (default ``5`` = yearly).

#         Returns
#         -------
#         pandas.DataFrame
#             Summed constituent time-series across PERLND segments.
#         """
#         return get_simulated_perlnd_constituent(self,constituent,time_step)

#     def get_implnd_constituent(self,constituent,implnd_ids = None,time_step = 5):
#         """Retrieve a summed impervious-land constituent time-series.

#         Parameters
#         ----------
#         constituent : str
#             High-level constituent abbreviation.
#         implnd_ids : list of int, optional
#             Reserved; currently unused.
#         time_step : int or str, optional
#             HSPF time-code (default ``5`` = yearly).

#         Returns
#         -------
#         pandas.DataFrame
#             Summed constituent time-series across IMPLND segments.
#         """
#         return get_simulated_implnd_constituent(self,constituent,time_step)

        
#     def get_reach_constituent(self,constituent,reach_ids,time_step,unit = None):
#         """Retrieve a reach constituent, dispatching to flow or temperature helpers.

#         Parameters
#         ----------
#         constituent : str
#             ``'Q'`` for flow, ``'WT'`` for water temperature, or any
#             water-quality constituent abbreviation.
#         reach_ids : list of int
#             Reach segment IDs.
#         time_step : int or str
#             HSPF time-code or frequency string.
#         unit : str, optional
#             Desired output unit (passed through to the underlying
#             retrieval function).

#         Returns
#         -------
#         pandas.DataFrame
#             Single-column DataFrame of the requested constituent.
#         """
#         if constituent == 'Q':
#             df = get_simulated_flow(self,time_step,reach_ids,unit = unit)
#         elif constituent == 'WT':
#             df = get_simulated_temperature(self,time_step,reach_ids)
#         else:     
#             df = get_simulated_reach_constituent(self,constituent,time_step,reach_ids,unit)
#         return df.to_frame()
    
#     def output_names(self):
#         """Return available output names merged across all HBN files.

#         Returns
#         -------
#         dict
#             Nested dictionary ``{operation: {activity: set_of_names}}``.
#         """
#         dics =  [hbn.output_names() for hbn in self.hbns]
#         return merge_dicts(dics)
#         # for dic in dics:
#         #     for operation, vals in dic.items():
#         #         for activity,v in vals.items():
#         #             [dd[operation][activity].add(t) for t in v]
#         # return dd

#     def _timeseries(self):
#         """Build a flat list of time-series descriptors from the merged map.

#         Returns
#         -------
#         list of list
#             Each inner list is ``[operation, id, activity, name]``.
#         """
#         mapn = self._mapn()
#         timeseries = []
#         for key, vals in mapn.items():
#             _key = list(key)
#             for val in vals:
#                 timeseries.append(_key + [val])
#         return timeseries      
            

#     def _mapn(self):
#         """Merge constituent-name maps from all underlying HBN files.

#         Returns
#         -------
#         collections.defaultdict
#             Mapping of ``(operation, id, activity)`` to a set of
#             constituent names.
#         """
#         dd = defaultdict(set)    
#         dics =  [hbn.mapn for hbn in self.hbns]
#         for dic in dics:
#             for key, vals in dic.items():
#                 [dd[key].add(val) for val in vals]
#         return dd 
    
#     def get_perlnd_data(self,constituent,t_code = 'yearly'):
#         """Retrieve all PERLND time-series for a constituent.

#         Parameters
#         ----------
#         constituent : str
#             High-level constituent abbreviation.
#         t_code : int or str, optional
#             HSPF time-code or frequency string (default ``'yearly'``).

#         Returns
#         -------
#         pandas.DataFrame
#             Concatenated time-series for the constituent's underlying
#             HBN names across all PERLND segments.
#         """
#         t_cons = constituents.get_tcons(constituent,'PERLND')
        
#         df = pd.concat([self.get_multiple_timeseries(t_opn = 'PERLND',
#                                      t_code = t_code,
#                                      t_con = t_con,
#                                      opnids = None)
#                          for t_con in t_cons],axis = 0)
        
#         return df
         
          
#     def get_rchres_output(self,constituent,units = 'mg/l',t_code = 5):
#         """Retrieve a summed RCHRES constituent used for calibration.

#         Convenience method that sums the underlying HBN time-series
#         names for *constituent* across all reach segments.

#         Parameters
#         ----------
#         constituent : str
#             High-level constituent abbreviation.
#         units : str, optional
#             Unit label attached to the result (default ``'mg/l'``).
#         t_code : int or str, optional
#             HSPF time-code (default ``5`` = yearly).

#         Returns
#         -------
#         pandas.DataFrame
#             Summed time-series with ``attrs`` for ``'unit'`` and
#             ``'constituent'``.
#         """
#         t_cons = constituents.get_tcons(constituent,'RCHRES',units)
#         df = sum([self.get_multiple_timeseries('RCHRES',t_code,t_con) for t_con in t_cons])
#         df.attrs['unit'] = units
#         df.attrs['constituent'] = constituent
#         return df
    
        
#     def reach_losses(self,constituent,t_code): 
#         """Compute the inflow-to-outflow ratio for a reach constituent.

#         Parameters
#         ----------
#         constituent : str
#             Constituent key present in :data:`LOSS_MAP`.
#         t_code : int or str
#             HSPF time-code or frequency string.

#         Returns
#         -------
#         pandas.Series
#             Ratio of total inflow to total outflow for each reach.
#         """
#         inflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][0]],axis=1).sum()
#         outflows = pd.concat([self.get_multiple_timeseries('RCHRES',t_code,t_cons) for t_cons in LOSS_MAP[constituent][1]],axis=1).sum()
#         return inflows/outflows
        
# # Inflow/outflow constituent names used to compute reach losses.
# LOSS_MAP = {'Q':(['IVOL'],['ROVOL']),
#        'TSS': (['ISEDTOT'],['ROSEDTOT']),
#        'TP': (['PTOTIN'],['PTOTOUT']),
#        'N': ([ 'NO2INTOT', 'NO3INTOT'],['NO3OUTTOT','NO2OUTTOT']),
#        'TKN':(['TAMINTOT','NTOTORGIN'],['TAMOUTTOT','NTOTORGOUT']),
#        'OP': (['PO4INDIS'],['PO4OUTDIS'])}
# # HSPF numeric output levels mapped to pandas frequency aliases.
# TCODES2FREQ = {
#     1: "min",
#     2: pandas_freq(OutputLevel.HOURLY),
#     3: pandas_freq(OutputLevel.DAILY),
#     4: pandas_freq(OutputLevel.MONTHLY),
#     5: pandas_freq(OutputLevel.YEARLY),
# }
    
# class hbnClass:
#     """Reader for a single HSPF binary output (HBN) file.

#     Parses the binary record layout of the ``.hbn`` file, builds an
#     in-memory index of constituent names (``mapn``) and data-record
#     positions (``mapd``), and lazily reads time-series data on demand.

#     Parameters
#     ----------
#     file_name : str or pathlib.Path
#         Path to the ``.hbn`` file.
#     Map : bool, optional
#         If ``True`` (default), the file is fully mapped on construction
#         via :meth:`map_hbn`.

#     Attributes
#     ----------
#     file_name : str or pathlib.Path
#         Path to the underlying binary file.
#     data : numpy.ndarray
#         Raw byte array of the file contents.
#     mapn : dict
#         ``{(operation, id, activity): [name, ...]}`` constituent-name
#         map.
#     mapd : dict
#         ``{(operation, id, activity, tcode): [(index, reclen), ...]}``
#         data-record position map.
#     data_frames : dict
#         Cache of already-read :class:`pandas.DataFrame` objects keyed
#         by summary index strings.
#     tcodes : dict
#         Bidirectional mapping between time-code integers and frequency
#         strings.
#     pandas_tcodes : dict
#         Time-code integers mapped to pandas offset aliases.
#     """

#     def __init__(self,file_name,Map = True):
#         self.file_name = str(file_name)
#         self.tcodes = {'minutely':1,'hourly':2,'daily':3,'monthly':4,'yearly':5,
#                        1:'minutely',2:'hourly',3:'daily',4:'monthly',5:'yearly',
#                        'min':1,'h':2,'D':3,'M':4,'Y':5,'H':2,'ME':4,'YE':5}
#         self.pandas_tcodes = TCODES2FREQ.copy()
        
#         # The two indexes — pure Python dicts, no file references.
#         self.mapn = {}
#         self.mapd = {}
        
#         self._clear_cache()
        
#         if Map:
#             self.map_hbn()


#     @contextmanager
#     def _open(self):
#         """Open the file briefly with mmap, yield it, close it on exit.
        
#         Used both during indexing and during data reads.  Because the
#         mmap is closed immediately after the `with` block ends, no
#         long-lived OS resource is held.
#         """
#         with open(self.file_name, 'rb') as fh:
#             mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
#             try:
#                 yield mm
#             finally:
#                 mm.close()

                            
#     def __del__(self):
#         # Release the mapping when the object is garbage collected
#         if hasattr(self, '_mmap'):
#             self._mmap.close()

#     def data(self,file_name,Map = False):
#         """Load raw bytes from an HBN file and optionally map its contents.

#         Parameters
#         ----------
#         file_name : str or pathlib.Path
#             Path to the ``.hbn`` file.
#         Map : bool, optional
#             If ``True``, call :meth:`map_hbn` after loading
#             (default ``False``).
#         """
#         self.file_name = file_name
#         with open(file_name, 'rb') as fh:
#             # Map entire file. ACCESS_READ = read-only, won't be modified.
#             self._mmap = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
#         self.data = np.frombuffer(self._mmap, dtype='B')
#         if self.data[0] != 0xFD:
#             print('BAD HBN FILE - must start with magic number 0xFD')
#             return
#         if Map == True:
#             self.map_hbn()
#         else:
#             self._clear_cache()
    
#     def map_hbn(self):
#         """Scan the file once, build mapn and mapd, then close the file."""
#         self._clear_cache()
#         mapn = defaultdict(list)
#         mapd = defaultdict(list)
        
#         with self._open() as mm:
#             if mm[0] != 0xFD:
#                 print('BAD HBN FILE - must start with magic number 0xFD')
#                 return
            
#             offset = 1
#             size = mm.size()
#             while offset < size:
#                 header = mm[offset:offset + 28]
#                 rc1, rc2, rc3, rc, rectype, op, id_, activity = unpack(
#                     '4BI8sI8s', header)
#                 rc1 = int(rc1 >> 2)
#                 rc2 = int(rc2) * 64 + rc1
#                 rc3 = int(rc3) * 16384 + rc2
#                 reclen = int(rc) * 4194304 + rc3 - 24
                
#                 op = op.decode('ascii').strip()
#                 activity = activity.decode('ascii').strip()
                
#                 if op not in {'PERLND', 'IMPLND', 'RCHRES'}:
#                     print('ALIGNMENT ERROR', op)
                
#                 if rectype == 1:
#                     tcode = unpack('I', mm[offset + 32:offset + 36])[0]
#                     mapd[op, id_, activity, tcode].append((offset, reclen))
#                 elif rectype == 0:
#                     body = mm[offset + 28:offset + 28 + reclen]
#                     slen = 0
#                     while slen < reclen:
#                         ln = unpack('I', body[slen:slen + 4])[0]
#                         n = unpack(f'{ln}s', body[slen + 4:slen + 4 + ln])[0]\
#                             .decode('ascii').strip()
#                         mapn[op, id_, activity].append(n)#.replace('-', ''))
#                         slen += 4 + ln
                
#                 cpos = reclen + 28
#                 if cpos < 64:       bp_width = 1
#                 elif cpos < 16384:  bp_width = 2
#                 else:               bp_width = 3
#                 offset += reclen + 28 + bp_width
#         # ← mmap and file handle are closed here, deterministically
        
#         self.mapn = dict(mapn)
#         self.mapd = dict(mapd)
    
#     def read_data(self,operation,id_,activity,tcode):
#         """Read and cache a single time-series DataFrame from the binary data.

#         Unpacks the raw bytes at the offsets stored in :attr:`mapd` and
#         builds a :class:`pandas.DataFrame` indexed by datetime.  The
#         result is resampled to regularise the time index and cached in
#         :attr:`data_frames`.

#         Parameters
#         ----------
#         operation : str
#             ``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``.
#         id_ : int
#             Operation segment ID.
#         activity : str
#             HSPF activity name (e.g. ``'HYDR'``).
#         tcode : int
#             HSPF numeric time-code (1–5).

#         Returns
#         -------
#         pandas.DataFrame or None
#             The resampled DataFrame, or ``None`` if no rows were found.
#         """
#         nvals = len(self.mapn[operation, id_, activity])
#         rows = []
#         times = []
#         record_offsets = self.mapd[operation, id_, activity, tcode]
        
#         # Open once for ALL the records of this query.
#         with self._open() as mm:
#             for (offset, reclen) in record_offsets:
#                 yr, mo, dy, hr, mn = unpack('5I', mm[offset + 36:offset + 56])
#                 row = unpack(f'{nvals}f',
#                              mm[offset + 56:offset + 56 + 4 * nvals])
#                 times.append(datetime(yr, mo, dy, 0, mn) + timedelta(hours=hr - 1))
#                 rows.append(row)

#         dfname = f'{operation}_{activity}_{id_:03d}_{tcode}'
#         if self.simulation_duration_count == 0:
#             self.simulation_duration_count = len(times)
#         df = DataFrame(rows, index=times, columns=self.mapn[operation, id_, activity]).sort_index(level = 'index')
#         if len(df) > 0:
#             #if tcode in ['daily',3]:
#             self.summaryindx.append(dfname)
#             self.summary.append((operation, activity, str(id_), self.tcodes[tcode], str(df.shape), df.index[0], df.index[-1]))
#             self.output_dictionary[dfname] = self.mapn[operation, id_, activity]
#             self.data_frames[dfname] = df.resample(self.pandas_tcodes[tcode]).mean() # sets the hours to 00 for non hourly time steps # an expensive operation probably
#             return self.data_frames[dfname]
#         else:
#             return None
    
#     def _clear_cache(self):
#         """Reset all cached DataFrames and summary structures."""
#         self.simulation_duration_count = 0

#         self.data_frames = {}
#         self.summary = []
#         self.summarycols = ['Operation', 'Activity', 'segment', 'Frequency', 'Shape', 'Start', 'Stop']
#         self.summaryindx = []
#         self.output_dictionary = {}

#     # def read_data2(self,operation,id,activity,tcode):

#     #     rows = []
#     #     times = []
        
#     #     nvals = len(self.mapn[operation, id, activity])  # number of constituent time series
#     #     #utc_offset = timezone(timedelta(hours=6))  # UTC is 6 hours ahead of CST
        
#     #     indices, reclens = zip(*self.mapd[operation, id, activity, tcode])
#     #     indices = np.array(indices)
#     #     data_array = np.frombuffer(self.data, dtype=np.uint8)  # Convert raw data to NumPy array
    
#     #     times = [np.frombuffer(data_array[indice+36:  indice+56], dtype=np.int32,count=5) for indice in indices]
#     #     times = [datetime(time[0],time[1],time[2],time[3]-1) for time in times]
#     #     rows =  [np.frombuffer(data_array[indice + 56:indice +56 + (4 * nvals)], dtype=np.float32) for indice in indices]
    
#     #     df = pd.DataFrame(rows, index=times, columns=self.mapn[operation, id, activity]).sort_index(level = 'index')
#     #     return df
   
#     def infer_opnids(self,t_opn, t_cons,activity):
#         """Infer operation segment IDs that contain a given constituent.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_cons : str
#             Constituent name to search for.
#         activity : str
#             HSPF activity name.

#         Returns
#         -------
#         list of int
#             Matching segment IDs, or ``[-1]`` if none are found.
#         """
#         result = [k[-2] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn) & (k[-1] == activity)]
#         if len(result) == 0:
#             result = [-1]
#         #     return print('No Constituent-OPNID relationship found')
#         return result
    
    
#     def infer_activity(self,t_opn, t_cons):  
#         """Infer the HSPF activity that contains a given constituent.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_cons : str
#             Constituent name to search for.

#         Returns
#         -------
#         str
#             The unique activity name, or an empty string if the
#             constituent is not found.

#         Raises
#         ------
#         AssertionError
#             If the constituent is found under more than one activity.
#         """
#         result = [k[-1] for k,v in self.mapn.items() if (t_cons in v) & (k[0] == t_opn)]
#         if len(result) == 0:
#             result = ''
#         else:#     return print('No Constituent-Activity relationship found')
#             assert(len(set(result)) == 1)
#             result = result[0]
#         return result
    
#     def get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
#         """Retrieve a single constituent time-series, raising on empty results.

#         Thin wrapper around :meth:`_get_time_series` that raises
#         :class:`ValueError` when no data is found.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_cons : str
#             Constituent name.
#         t_code : int or str
#             HSPF time-code or frequency string.
#         opnid : int
#             Operation segment ID.
#         activity : str, optional
#             HSPF activity name.  Inferred when ``None``.

#         Returns
#         -------
#         pandas.Series
#             The requested time-series.

#         Raises
#         ------
#         ValueError
#             If the underlying query returns an empty DataFrame.
#         """
#         df = self._get_time_series(t_opn, t_cons, t_code, opnid, activity)
#         if df.empty:
#             raise ValueError(f"No data found for {t_opn} {t_cons} {t_code} {opnid} {activity}")
#         return df

#     def _get_time_series(self, t_opn, t_cons, t_code, opnid, activity = None):
#         """Retrieve a single constituent time-series from the HBN file.

#         Looks up or reads the requested record, extracts the column for
#         *t_cons*, and filters to dates on or after 1996-01-01.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         t_cons : str
#             Constituent name.
#         t_code : int or str
#             HSPF time-code or frequency string.
#         opnid : int
#             Operation segment ID.
#         activity : str, optional
#             HSPF activity name.  Inferred when ``None``.

#         Returns
#         -------
#         pandas.Series or pandas.DataFrame
#             The time-series for *t_cons*, or an empty DataFrame if the
#             record is not present.
#         """


#         if isinstance(t_code,str):
#             t_code = self.tcodes[t_code]
        
#         if activity is None:
#             activity = self.infer_activity(t_opn,t_cons)        

            
#         summaryindx = f'{t_opn}_{activity}_{opnid:03d}_{t_code}'
#         if summaryindx in self.summaryindx:
#             df = self.data_frames[summaryindx][t_cons].copy()
#             #df.index = df.index.shift(-1,TCODES2FREQ[t_code])
#             df = df[df.index >= '1996-01-01']
            
#         elif (t_opn, opnid, activity,t_code) in self.mapd.keys():
#             df =  self.read_data(t_opn,opnid,activity,t_code)[t_cons].copy()
#             #df.index = df.index.shift(-1,TCODES2FREQ[t_code])
#             df = df[df.index >= '1996-01-01']
#         else:
#             df = pd.DataFrame()
        
#         df.index.name = 'datetime'
#         return df

#     def get_output(self,operation,opnid,activity,tcode):
#         summaryindx = f'{operation}_{activity}_{opnid:03d}_{tcode}'
#         if summaryindx in self.summaryindx:
#             df = self.data_frames[summaryindx].copy()
#             #df.index = df.index.shift(-1,TCODES2FREQ[tcode])
#         elif (operation, opnid, activity,tcode) in self.mapd.keys():
#             df =  self.read_data(operation,opnid,activity,tcode).copy()
#             #df.index = df.index.shift(-1,TCODES2FREQ[tcode])
#         else:
#             df = pd.DataFrame()
#         df.index.name = 'datetime'
#         return df
    
#     def get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
#         """Retrieve a constituent across multiple segments, raising on empty results.

#         Thin wrapper around :meth:`_get_multiple_timeseries` that
#         raises :class:`ValueError` when no data is found.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type.
#         t_code : int or str
#             HSPF time-code or frequency string.
#         t_con : str
#             Constituent name.
#         opnids : list of int, optional
#             Segment IDs.  If ``None``, inferred from :attr:`mapn`.
#         activity : str, optional
#             HSPF activity name.  Inferred when ``None``.

#         Returns
#         -------
#         pandas.DataFrame
#             Wide-format DataFrame with one column per segment.

#         Raises
#         ------
#         ValueError
#             If the underlying query returns an empty DataFrame.
#         """
#         df = self._get_multiple_timeseries(t_opn,t_code,t_con,opnids,activity)
#         if df.empty:
#             raise ValueError(f"No data found for {t_opn} {t_con} {t_code} {opnids} {activity}")
#         return df
    
#     def _get_multiple_timeseries(self,t_opn,t_code,t_con,opnids = None,activity = None):
#         """Retrieve a single constituent for multiple segments.

#         Parameters
#         ----------
#         t_opn : str
#             Operation type.
#         t_code : int or str
#             HSPF time-code or frequency string.
#         t_con : str
#             Constituent name.
#         opnids : list of int, optional
#             Segment IDs.  If ``None``, inferred from :attr:`mapn`.
#         activity : str, optional
#             HSPF activity name.  Inferred when ``None``.

#         Returns
#         -------
#         pandas.DataFrame
#             Wide-format DataFrame with one column per segment, or an
#             empty DataFrame if no matching records exist.
#         """

        
#         if isinstance(t_code,str):
#             t_code = self.tcodes[t_code]
            
#         if activity is None:
#             activity = self.infer_activity(t_opn,t_con)   

#         if opnids is None:
#             opnids = self.infer_opnids(t_opn,t_con,activity)

           
#         df = pd.DataFrame()
#         frames = []
#         mapd_list = list(self.mapd.keys())
#         for opnid in opnids:
#             if (t_opn,opnid,activity,t_code) in mapd_list:
#                 frames.append(self.get_time_series(t_opn,t_con,t_code,opnid,activity).rename(opnid))
#         if len(frames)>0:
#             df = pd.concat(frames,axis=1)
        
#         return df
    
#     def output_names(self):
#         """Return constituent names grouped by activity.

#         .. note::

#            This definition is overridden by the subsequent
#            :meth:`output_names` which groups by operation *and*
#            activity.

#         Returns
#         -------
#         dict
#             ``{activity: set_of_names}``.
#         """
#         activities = set([k[-1] for k,v in self.mapn.items()])
#         dic = {}
#         for activity in activities:
#             t_cons = [v for k,v in self.mapn.items() if k[-1] == activity]   
#             dic[activity] = set([item for sublist in t_cons for item in sublist])
#         return dic
    
    
#     def output_names(self):
#         """Return constituent names grouped by operation and activity.

#         This definition supersedes the earlier :meth:`output_names`
#         that groups only by activity.

#         Returns
#         -------
#         dict
#             Nested dictionary
#             ``{operation: {activity: set_of_names}}``.
#         """

#         activities = []
#         operations = []
#         for k, v in self.mapn.items():
#             operations.append(k[0])
#             activities.append(k[-1])

#         operations = set(operations)
#         activities = set(activities)
#         #activities = set([k[-1] for k,v in self.mapn.items()])

#         dic = {}
#         for operation in operations:
#             acitivities = set([k[-1] for k,v in self.mapn.items() if k[0] == operation])
#             dic[operation] = {}
#             for activity in acitivities:
#                 t_cons = [v for k,v in self.mapn.items() if (k[0] == operation) & (k[-1] == activity)]   
#                 dic[operation][activity] = set([item for sublist in t_cons for item in sublist])
#         # for activity in activities:
#         #     t_cons = [v for k,v in self.mapn.items() if k[-1] == activity]   
#         #     dic[activity] = set([item for sublist in t_cons for item in sublist])
#         return dic
    
#     def get_timeseries(self):
#         """Build a flat list of time-series descriptors from :attr:`mapn`.

#         Returns
#         -------
#         list of list
#             Each inner list is ``[operation, id, activity, name]``.
#         """
#         mapn = self.mapn
#         timeseries = []
#         for key, vals in mapn.items():
#             _key = list(key)
#             for val in vals:
#                 timeseries.append(_key + [val])
#         return timeseries      

#     @staticmethod          
#     def get_perlands(summary_indxs):
#          """Extract PERLND segment IDs from summary index strings.

#          Parameters
#          ----------
#          summary_indxs : list of str
#              Summary index strings in the format
#              ``'<OPN>_<ACTIVITY>_<ID>_<TCODE>'``.

#          Returns
#          -------
#          list of int
#              Extracted integer segment IDs.
#          """
#          perlands =  [int(summary_indx.split('_')[-2]) for summary_indx in summary_indxs]
#          return perlands

#     def get_block(self, operation, activity, tcode):
#         """Read a block of time-series data for a given operation, activity, and time-code.

#         Parameters
#         ----------
#         operation : str
#             Operation type (``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``).
#         activity : str
#             HSPF activity name.
#         tcode : int or str
#             HSPF time-code or frequency string.

#         Returns
#         -------
#         pandas.DataFrame
#             Concatenated DataFrame of all segments for the specified operation, activity, and time-code.
#         """
#         if isinstance(tcode, str):
#             tcode = self.tcodes[tcode]

#         df_list = []
#         for (opn, id_, act, tc), _ in self.mapd.items():
#             if opn == operation and act == activity and tc == tcode:
#                 df = self.get_output(operation, id_, activity, tcode)
#                 df['OPNID'] = id_
#                 df.reset_index(drop=False, inplace=True)
#                 #set opnid and datetime as first columns
#                 if df is not None:
#                     df_list.append(df)

#         if df_list:
#             df = pd.concat(df_list, axis=0)
#             df = df[['OPNID', 'datetime'] + [col for col in df.columns if col not in ['OPNID', 'datetime']]]
#         else:
#             df = pd.DataFrame()
#         return df

# def merge_dicts(dicts):
#     """Merge a list of dictionaries, combining sets at the leaf level.

#     Recursively walks each dictionary.  When both sides have a
#     ``dict`` for the same key the merge recurses; when both sides
#     have a ``set`` the sets are unioned.  Incompatible types for the
#     same key raise :class:`ValueError`.

#     Parameters
#     ----------
#     dicts : list of dict
#         Dictionaries to merge.

#     Returns
#     -------
#     dict
#         The merged dictionary.

#     Raises
#     ------
#     ValueError
#         If the same key maps to incompatible types across
#         dictionaries.
#     """
#     def recursive_merge(d1, d2):
#         for key, value in d2.items():
#             if key in d1:
#                 # If the value is a dictionary, recurse
#                 if isinstance(d1[key], MutableMapping) and isinstance(value, MutableMapping):
#                     recursive_merge(d1[key], value)
#                 # If the value is a set, merge the sets
#                 elif isinstance(d1[key], set) and isinstance(value, set):
#                     d1[key].update(value)
#                 else:
#                     raise ValueError(f"Incompatible types for key '{key}': {type(d1[key])} vs {type(value)}")
#             else:
#                 # If the key does not exist in d1, copy it
#                 d1[key] = value
    
#     # Start with an empty dictionary
#     merged_dict = {}
    
#     for d in dicts:
#         recursive_merge(merged_dict, d)
    
#     return merged_dict
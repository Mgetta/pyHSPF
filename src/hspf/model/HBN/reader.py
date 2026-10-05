
from dataclasses import dataclass
from datetime import timedelta, datetime
import mmap
import numpy as np
import pandas as pd
from pandas import DataFrame
from contextlib import contextmanager
from collections import defaultdict
from struct import unpack


from hspf.core.conventions import pandas_freq
from hspf.core.types import Activity, OutputLevel, Block, EntityType, EntityRef


TCODES2FREQ = {
    1: "min",
    2: pandas_freq(OutputLevel.HOURLY),
    3: pandas_freq(OutputLevel.DAILY),
    4: pandas_freq(OutputLevel.MONTHLY),
    5: pandas_freq(OutputLevel.YEARLY),
}

@dataclass(frozen=True)
class HbnRecordKey:
    entity: EntityRef
    activity: Activity
    output_level: OutputLevel

    
@dataclass
class HbnRecord:
    record_key: HbnRecordKey
    columns : tuple[str, ...]
    offsets: tuple[tuple[int, int], ...]

    def to_block(self) -> Block:
        return Block(self.record_key.entity.entity_type, self.record_key.activity, self.record_key.output_level)

class HbnFile:
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

    def __init__(self,file_name):
        self.file_name = str(file_name)
        self.tcodes = {'minutely':1,'hourly':2,'daily':3,'monthly':4,'yearly':5,
                       1:'minutely',2:'hourly',3:'daily',4:'monthly',5:'yearly',
                       'min':1,'h':2,'D':3,'M':4,'Y':5,'H':2,'ME':4,'YE':5}
        self.pandas_tcodes = TCODES2FREQ.copy()
        


    @contextmanager
    def _open(self):
        """Open the file briefly with mmap, yield it, close it on exit.
        
        Used both during indexing and during data reads.  Because the
        mmap is closed immediately after the `with` block ends, no
        long-lived OS resource is held.
        """
        with open(self.file_name, 'rb') as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                yield mm
            finally:
                mm.close()

                            
    def __del__(self):
        # Release the mapping when the object is garbage collected
        if hasattr(self, '_mmap'):
            self._mmap.close()


    def scan(self):
        """Scan the file once, build mapn and mapd, then close the file."""
        mapn = defaultdict(list)
        mapd = defaultdict(list)
        with self._open() as mm:
            if mm[0] != 0xFD:
                print('BAD HBN FILE - must start with magic number 0xFD')
                return
            
            offset = 1
            size = mm.size()
            while offset < size:
                header = mm[offset:offset + 28]
                rc1, rc2, rc3, rc, rectype, op, id_, activity = unpack(
                    '4BI8sI8s', header)
                rc1 = int(rc1 >> 2)
                rc2 = int(rc2) * 64 + rc1
                rc3 = int(rc3) * 16384 + rc2
                reclen = int(rc) * 4194304 + rc3 - 24
                
                op = EntityType(op.decode('ascii').strip())
                activity = Activity(activity.decode('ascii').strip())
                
                
                if rectype == 1:
                    tcode = unpack('I', mm[offset + 32:offset + 36])[0]
                    tcode = OutputLevel(tcode)
                    mapd[op, id_, activity, tcode].append((offset, reclen))
                elif rectype == 0:
                    body = mm[offset + 28:offset + 28 + reclen]
                    slen = 0
                    while slen < reclen:
                        ln = unpack('I', body[slen:slen + 4])[0]
                        n = unpack(f'{ln}s', body[slen + 4:slen + 4 + ln])[0]\
                            .decode('ascii').strip()
                        mapn[op, id_, activity].append(n)#.replace('-', ''))
                        slen += 4 + ln
                
                cpos = reclen + 28
                if cpos < 64:       bp_width = 1
                elif cpos < 16384:  bp_width = 2
                else:               bp_width = 3
                offset += reclen + 28 + bp_width
        # ← mmap and file handle are closed here, deterministically
        
        # Return the final records dictionary
        mapn = dict(mapn)
        mapd = dict(mapd)
        records = {}
        for (op, id_, activity, tcode), offsets in mapd.items():
            record_key = HbnRecordKey(
                entity=EntityRef(op, id_),
                activity=activity,
                output_level=tcode,
            )

            mapn_key = (op, id_, activity)
            if mapn_key not in mapn:
                raise ValueError(f"No HBN name record found for {record_key}")

            records[record_key] = HbnRecord(
                record_key=record_key,
                columns=tuple(mapn[mapn_key]),
                offsets=tuple(offsets),
            )

        return records

    def decode(self, record: HbnRecord) -> pd.DataFrame:
        """Pure transform: locator -> DataFrame. No mutation, no caching here."""
        rows, times = [], []
        with self._open() as mm:
            for offset, _ in record.offsets:
                yr, mo, dy, hr, mn = unpack('5I', mm[offset+36:offset+56])
                rows.append(unpack(f'{len(record.columns)}f', mm[offset+56:offset+56+4*len(record.columns)]))
                times.append(datetime(yr, mo, dy, 0, mn) + timedelta(hours=hr - 1))
        df = DataFrame(rows, index=pd.DatetimeIndex(times, name="datetime"), columns=record.columns)
        df.attrs.update(entity=record.record_key.entity, activity=record.record_key.activity, tcode=record.record_key.output_level)
        return df.sort_index()
    
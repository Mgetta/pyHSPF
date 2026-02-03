# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 15:33:52 2022
Utility functions for accessing data from the hbn files as they relate to the
nutrients relevant for our current calibration methods. (See calibration_helpers.py)

@author: mfratki
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
#             comments = ' '.join(values[6:]).strip('
')
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

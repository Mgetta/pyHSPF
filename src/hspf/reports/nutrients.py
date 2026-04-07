# -*- coding: utf-8 -*-
"""
Phosphorous loading calculations — masslink scheme and qualprop transforms.
"""
import pandas as pd

#: Conversion factors to translate BOD oxygen demand into equivalent phosphorus and nitrogen mass loadings.
_BOD_PHOSPHORUS_CONVERSION = 0.007326
_BOD_NITROGEN_CONVERSION = 0.052938

#: Mapping of phosphorus species to MASS-LINK table member identifiers.
#:
#: Each key is a phosphorus component name and each value is a dict with
#: ``tmemn`` (target member name), ``tmemsb1`` (target member subscript 1),
#: and ``tmemsb2`` (target member subscript 2) used to look up the
#: corresponding MASS-LINK entry in the UCI file.
MASSLINK_SCHEME = {
    'dissolved_orthophosphate': {'tmemn': 'NUIF1',
                                                'tmemsb1': '4',
                                                'tmemsb2':''},
                'particulate_orthophosphate_sand': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '1',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_silt': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '2',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_clay': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '3',
                                                    'tmemsb2':'2'},
                'organic_refactory_phosphorous': {'tmemn': 'PKIF',
                                                  'tmemsb1' : '4',
                                                  'tmemsb2':''},
                'organic_refactory_carbon':{'tmemn' : 'PKIF',
                                            'tmemsb1': '5',
                                            'tmemsb2':''},
                'labile_oxygen_demand_phosphorous': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':''},
                'dissolved_total_ammonia': {'tmemn': 'NUIF1',
                                  'tmemsb1': '2',
                                  'tmemsb2':''},
                'dissolved_nitrate': {'tmemn': 'NUIF1',
                                  'tmemsb1': '1',
                                  'tmemsb2':''},
                'organic_refactory_nitrogen': {'tmemn': 'PKIF',
                                         'tmemsb1': '3',
                                         'tmemsb2':''},
                'labile_oxygen_demand_nitrogen': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':'',
                                         }
}

def _calculate_BOD_nitrogen(uci):
    table = uci.table('RCHRES','CONV-VAL1',0)
    conversions = 14* table['BPCNTC']*table['CVBPN']/(12*100*table['CVBPC'] * table['CVBO'])
    conversions.name = 'TN_BOD_CONVERSION'
    return conversions

def _calculate_BOD_phosphorus(uci):
    table = uci.table('RCHRES','CONV-VAL1',0)
    conversions = 31* table['BPCNTC']/(12*100*table['CVBPC'] * table['CVBO'])
    conversions.name = 'TP_BOD_CONVERSION'
    return conversions


def _valid_timeseries():
    """List of valid timeseries names that can be extracted via the MASS-LINK scheme."""
    return list(MASSLINK_SCHEME.keys())

def get_timeseries(ts_name,uci,hbn,operation,mlno,t_code = 4):
    """
    Retrieve and transform modeled timeseries loadings for a given constituent
    by applying mass-link partitioning factors.

    This function extracts timeseries data from an HBN (binary output) file for a
    specified operation and transforms it using the mass-link scheme. This is
    necessary when direct model outputs from operations (e.g., PERLNDS, IMPLNDS)
    are partitioned across different pathways via the MASS-LINK block in the UCI
    file. The mass-link member number determines how the raw output is distributed
    among receiving targets.

    Valid timeseries names that can be retrieved are:
    - 'dissolved_orthophosphate'
    - 'particulate_orthophosphate_sand'
    - 'particulate_orthophosphate_silt'
    - 'particulate_orthophosphate_clay'
    - 'particulate_orthophosphate'
    - 'organic_refactory_phosphorous'
    - 'organic_refactory_carbon'
    - 'labile_oxygen_demand_phosphorous'
    - 'dissolved_total_ammonia'
    - 'dissolved_nitrate'
    - 'organic_refactory_nitrogen'
    - 'labile_oxygen_demand_nitrogen'

    :param ts_name: The name of the timeseries constituent to retrieve, used as
        a key into the ``MASSLINK_SCHEME`` dictionary to look up the appropriate
        target member name and sub-member identifiers.
    :type ts_name: str
    :param uci: The parsed UCI object containing the
        model configuration, including mass-link definitions.
    :type uci: object
    :param hbn: The HBN file object containing
        the raw modeled timeseries results.
    :type hbn: object
    :param operation: The HSPF operation identifier (e.g., ``'PERLND'``,
        ``'IMPLND'``) from which the timeseries originates.
    :type operation: str
    :param mlno: The MASS-LINK member number that specifies the MASS-LINK table to use when partitioning
        pathways for the constituent.
    :type mlno: int
    :param t_code: The time code specifying the temporal resolution of the
        output timeseries. Defaults to ``4`` (monthly).
    :type t_code: int, optional

    :return: The transformed timeseries loadings after applying the mass-link
        partitioning factors.
    :rtype: pandas.Series or pandas.DataFrame
    """
    """Calculates timeseries loadings for a given constituent from the operation and MASS-LINK member identifiers."""
    
    assert ts_name in _valid_timeseries(), f"Invalid timeseries name '{ts_name}'. Valid options are: {_valid_timeseries()}"
    
    tmemn = MASSLINK_SCHEME[ts_name]['tmemn']
    tmemsb1 = MASSLINK_SCHEME[ts_name]['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME[ts_name]['tmemsb2']
    return _qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)


def total_nitrogen(uci,hbn,t_code,operation = 'PERLND',constituents = None,pathways = None):
    """Compute total nitrogen loading for all OPNIDs in an operation.

    Sums dissolved nitrate, dissolved total ammonia, organic refractory
    nitrogen, and a converted labile oxygen demand component (BOD × 0.052938
    factor) across all MASS-LINK groups.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    operation : str, optional
        Operation type (default ``'PERLND'``).

    Returns
    -------
    pd.DataFrame
        Total nitrogen timeseries with OPNID columns and DatetimeIndex.
    """
    if constituents is None:
        constituents = ['dissolved_total_ammonia',
                        'dissolved_nitrate',
                        'organic_refactory_nitrogen',
                        'labile_oxygen_demand_nitrogen']


    opnids = uci.network.subwatersheds()
    opnids = list(set(uci.table('SCHEMATIC').query('TVOL == "RCHRES" & SVOL == @operation')['SVOLNO'].to_list()))
    #opnids = opnids.join(_calculate_BOD_phosphorus(uci).to_frame())
    
    

    total = get_timeseries(uci,hbn,operation,constituents,pathways,t_code)[opnids]
    return total
    

def total_phosphorus(uci,hbn,t_code,operation = 'PERLND',constituents = None,pathways = None):
    """Compute total phosphorus loading for all OPNIDs in an operation.

    Sums dissolved orthophosphate, particulate orthophosphate, organic
    refractory phosphorus, and a converted labile oxygen demand component
    (BOD × 0.007326) across all MASS-LINK groups.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    operation : str, optional
        Operation type (default ``'PERLND'``).

    Returns
    -------
    pd.DataFrame
        Total phosphorus timeseries with OPNID columns and DatetimeIndex.
    """
    if constituents is None:
        constituents = ['dissolved_orthophosphate',
                        'particulate_orthophosphate_sand',
                        'particulate_orthophosphate_clay',
                        'particulate_orthophosphate_silt',
                        'organic_refactory_phosphorous',
                        'labile_oxygen_demand_phosphorous']


    opnids = uci.network.subwatersheds()
    opnids = list(set(uci.table('SCHEMATIC').query('TVOL == "RCHRES" & SVOL == @operation')['SVOLNO'].to_list()))
    #opnids = opnids.join(_calculate_BOD_phosphorus(uci).to_frame())
    
    

    total = get_timeseries(uci,hbn,operation,constituents,pathways,t_code)[opnids]
    return total

def _pathway_transform(uci, hbn, operation, mlno, ts_name, pathways=None, t_code=4):
    
    tmemn = MASSLINK_SCHEME[ts_name]['tmemn']
    tmemsb1 = MASSLINK_SCHEME[ts_name]['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME[ts_name]['tmemsb2']
    
    masslink = uci.table('MASS-LINK', f'MASS-LINK{mlno}')
    masslink = masslink.loc[
        (masslink['TMEMN'] == tmemn) &
        (masslink['TMEMSB1'] == tmemsb1) &
        (masslink['TMEMSB2'] == tmemsb2)
    ]
    masslink.fillna({'MFACTOR': 1}, inplace=True)
    
    if pathways is not None:
        masslink = masslink.loc[masslink['SMEMN'].isin(pathways)]

    if masslink.empty:
        return None  # <-- consistent "no data" sentinel

    parts = []
    for _, row in masslink.iterrows():
        hbn_name = row['SMEMN']
        if hbn_name in ['IOQUAL', 'SOQUAL', 'POQUAL', 'AOQUAL']:
            qual_name = uci.table(
                operation, 'QUAL-PROPS', int(row['SMEMSB1']) - 1
            ).iloc[0]['QUALID']
            hbn_name = row['SMEMN'] + qual_name
        mfactor = row['MFACTOR']
        parts.append(hbn.get_multiple_timeseries(row['SVOL'], t_code, hbn_name) * mfactor)

    ts = parts[0]
    for part in parts[1:]:
        ts = ts + part

    if ts_name == 'labile_oxygen_demand_phosphorous':
        ts = ts * _BOD_PHOSPHORUS_CONVERSION
    elif ts_name == 'labile_oxygen_demand_nitrogen':
        ts = ts * _BOD_NITROGEN_CONVERSION

    return ts


def get_timeseries(uci, hbn, operation, ts_names, pathways=None, t_code=5):

    subset = uci.table('SCHEMATIC').query('SVOL == @operation')

    totals = []
    for mlno in subset['MLNO'].unique():
        weight = (subset.query('MLNO == @mlno').groupby('SVOLNO')['AFACTR'].sum()/ subset.groupby('SVOLNO')['AFACTR'].sum())

        # Collect per-ts_name results, dropping Nones
        parts = [_pathway_transform(uci, hbn, operation, mlno, ts_name, pathways, t_code)
            for ts_name in ts_names
        ]
        parts = [p for p in parts if p is not None]
        if not parts:
            continue  # <-- nothing to contribute, skip this mlno entirely

        _ts = parts[0]
        for part in parts[1:]:
            _ts = _ts + part

        _ts = _ts[weight.index]
        totals.append(_ts * weight)

    if not totals:
        return pd.DataFrame()  # <-- caller gets a single, predictable type

    ts = pd.concat(totals, axis=1).T.groupby(level=0).sum().T
    return ts

def _qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2 = '',t_code = 4):
    """Apply a QUAL-PROP mass-link transform to extract a constituent timeseries.

    Reads the MASS-LINK table for the given member identifiers, applies
    the multiplication factor (MFACTOR), and sums across all matching
    source members.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    operation : str
        Operation type (e.g. ``'PERLND'``, ``'IMPLND'``).
    mlno : int
        MASS-LINK number in the UCI file.
    tmemn : str
        Target member name (e.g. ``'NUIF1'``, ``'PKIF'``).
    tmemsb1 : str
        Target member subscript 1.
    tmemsb2 : str, optional
        Target member subscript 2 (default ``''``).
    t_code : int, optional
        HBN time-step code (default 4 = monthly).

    Returns
    -------
    pd.DataFrame
        Summed timeseries across matching MASS-LINK entries.
    """
    masslink = uci.table('MASS-LINK',f'MASS-LINK{mlno}')
    masslink = masslink.loc[(masslink['TMEMN'] == tmemn) & (masslink['TMEMSB1'] == tmemsb1) & (masslink['TMEMSB2'] == tmemsb2)]
    masslink.fillna({'MFACTOR': 1}, inplace=True)
    ts = 0
    for index,row in masslink.iterrows():
        hbn_name = row['SMEMN']
        if hbn_name in ['IOQUAL','SOQUAL','POQUAL','AOQUAL']:
            qual_name = uci.table(operation,'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
            hbn_name = row['SMEMN'] + qual_name
        mfactor = row['MFACTOR']
        ts = hbn.get_multiple_timeseries(row['SVOL'],t_code,hbn_name)*mfactor + ts
    return ts
# constituents = ['particulate_orthophosphate_sand',
# 'particulate_orthophosphate_clay',
# 'particulate_orthophosphate_silt',
# 'dissolved_orthophosphate']


def fetch_single_timeseries(uci,hbn,ts_name,operation,opnid):

    subset = uci.table('SCHEMATIC').query('SVOL == @operation & SVOLNO == @opnid')
    ts = 0
    constituent = ts_name
    for mlno in subset['MLNO'].unique():
        weight = subset.query('MLNO == @mlno')['AFACTR'].sum()/subset['AFACTR'].sum()
        _ts = get_timeseries(constituent,uci,hbn,operation,mlno,5)
        if isinstance(_ts, (int, float)):
            ts = ts + _ts*weight

        else:
            _ts = _ts[opnid]
            ts = ts + _ts*weight
    return ts



# 'ORTHO P (PQUAL' : {'Surface Flow with Sediment' : ['particulate_orthophosphate_sand',
#                                                     'particulate_orthophosphate_clay',
#                                                     'particulate_orthophosphate_silt'],
#                     'Interflow': ['Dissolved_orthophosphate']}
# opnids = df.loc[abs(df['exp']) > .001].index
# nutrients.MASSLINK_SCHEME['dissolved_orthophosphate']
# pathway = 'SOQUAL'
# tmemn = 'OXIF'
# tmemsb1 = '2'
# tmemsb2 = ''
# operation = 'PERLND'
# opnid = 10
# table = uci.table('SCHEMATIC').query('SVOL == "PERLND" & SVOLNO == @opnid')
# mlnos = list(table['MLNO'].unique())

# # vals = []
# # for opnid in df.index:
# #     table = uci.table('SCHEMATIC').query('SVOL == "PERLND" & SVOLNO == @opnid')
# #     mlnos = list(table['MLNO'].unique())
# #     vals.append(len(mlnos))
# #df['mlnos'] = vals
    

# schematic = uci.table('SCHEMATIC')
# masslinks = []
# for table_name in uci.table_names('MASS-LINK'):
#     masslink = uci.table('MASS-LINK',table_name)
#     masslink['MLNO'] = table_name.split('MASS-LINK')[1]
#     masslinks.append(masslink)
# masslinks = pd.concat(masslinks)
# masslinks['MFACTOR'] = masslinks['MFACTOR'].fillna(1)

# df = pd.merge(schematic,masslinks,left_on=['SVOL','MLNO','TVOL'],right_on=['SVOL','MLNO','TVOL'])
# df['TMEMSB1'] = df.apply(lambda row: row['TMEMSB1_x'] if row['TMEMSB1_x'] != '' else row['TMEMSB1_y'], axis=1)
# df['TMEMSB2'] = df.apply(lambda row: row['TMEMSB2_x'] if row['TMEMSB2_x'] != '' else row['TMEMSB2_y'], axis=1)


# constituents = ['dissolved_orthophosphate',
#  'particulate_orthophosphate_sand',
#  'particulate_orthophosphate_silt',
#  'particulate_orthophosphate_clay',
#  'organic_refactory_phosphorous',
#  'labile_oxygen_demand_phosphorous']
# total = 0
# pathways =  ['IOQUAL','SOQUAL','POQUAL','AOQUAL']
# pathway = 'IOQUAL'
# opnid = 39
# tvolno = 12
# operation = 'PERLND'
# for constituent in constituents:
#     tmemn = nutrients.MASSLINK_SCHEME[constituent]['tmemn']
#     tmemsb1 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb1']
#     tmemsb2 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb2']    
#     sources = masslinks.loc[masslinks['SVOL'].isin(['PERLND','IMPLND'])].reset_index()
#     sources['hbn_name'] = sources['SMEMN']
#     for index, row in sources.iterrows():
#         if (row['SMEMSB1'] != ''):
#             qual_name = uci.table(row['SVOL'],'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
#             hbn_name = row['SMEMN'] + qual_name
#             sources.loc[index,'hbn_name'] = hbn_name
#     sources = sources.query('TMEMN == @tmemn & TMEMSB1 == @tmemsb1 & TMEMSB2 == @tmemsb2')
#     df = pd.merge(schematic,sources,left_on=['SVOL','MLNO','TVOL'],right_on=['SVOL','MLNO','TVOL'])


# operation = 'PERLND'
# opnid = 10
# pathway = 'AOQUAL'
# tmemn = 'NUIF1'
# tmemsb1 = '4'
# tmemsb2 = ''
# subset = uci.table('SCHEMATIC').query('SVOL == "PERLND" & SVOLNO == 10')
# for mlno in subset['MLNO']:
#     masslink = uci.table('MASS-LINK', f'MASS-LINK{mlno}').fillna(1)
#     masslink = masslink.query('SMEMN == @pathway & TMEMN == @tmemn & TMEMSB1 == @tmemsb1 & TMEMSB2 == @tmemsb2')
#     qual_name = uci.table(operation,'QUAL-PROPS', int(masslink['SMEMSB1']) - 1).iloc[0]['QUALID']
#     hbn_name = masslink['SMEMN'] + qual_name
#     ts = hbn.get_multiple_timeseries(operation,t_code,hbn_name.values[0],opnids =[opnid])



#     for index,row in df.


#     table = df.query('SVOL == @operation')
#     #table = df.query('SVOL == "PERLND" & SVOLNO == @opnid & TVOLNO == @tvolno')
#     table = df.query('SVOL == "PERLND" & SVOLNO == @opnid')
#     table = table.query('TMEMN == @tmemn & TMEMSB1 == @tmemsb1 & TMEMSB2 == @tmemsb2')
#     table['MFACTOR'] = table['MFACTOR'].fillna(1)

#     ts = 0
#     areas = 0
#     count = 0
#     for index,row in table.iterrows():
#         hbn_name = row['SMEMN']
#         if hbn_name in pathways:
#             qual_name = uci.table(operation,'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
#             hbn_name = row['SMEMN'] + qual_name
#             mfactor = row['MFACTOR']
#             afactor = row['AFACTR']
#             ts = hbn.get_multiple_timeseries(row['SVOL'],t_code,hbn_name,opnids = [row['SVOLNO']])*mfactor   + ts
#             areas = areas + afactor
#             count = count + 1
#     if constituent == 'labile_oxygen_demand_phosphorous':
#         ts = ts*nutrients._BOD_PHOSPHORUS_CONVERSION
#     elif constituent == 'labile_oxygen_demand_nitrogen':
#         ts = ts*nutrients._BOD_NITROGEN_CONVERSION

#     total = ts + total
# #area = table.groupby(['TVOL','TVOLNO'])['AFACTR'].sum().sum()
# ts = ts/areas

# areas = schematic.groupby(['SVOL','SVOLNO','MLNO'])['AFACTR'].sum().reset_index()

# constituent = 'dissolved_orthophosphate'
# operation = 'PERLND'
# tmemn = nutrients.MASSLINK_SCHEME[constituent]['tmemn']
# tmemsb1 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb1']
# tmemsb2 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb2']
# table = masslinks.query('TMEMN == @tmemn & TMEMSB1 == @tmemsb1 & TMEMSB2 == @tmemsb2')
# table = table.query('SVOL == @operation')
# dfs = []
# for index,row in table.iterrows():
#         hbn_name = row['SMEMN']
#         if hbn_name in pathways:
#             qual_name = uci.table(operation,'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
#             hbn_name = row['SMEMN'] + qual_name
#             df = hbn.get_multiple_timeseries(row['SVOL'],t_code,hbn_name)*mfactor
#             df = df.mean().reset_index()
#             #df = df.reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
#             df['mlno'] = row['MLNO']
#             df['constituent'] = constituent
#             df['SVOL'] = row['SVOL']
#             dfs.append(df)


# operation = 'PERLND'
# constituent = 'dissolved_orthophosphate'
# tmemn = nutrients.MASSLINK_SCHEME[constituent]['tmemn']
# tmemsb1 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb1']
# tmemsb2 = nutrients.MASSLINK_SCHEME[constituent]['tmemsb2']
# table = df.query('SVOL == @operation')
# sources = table.query('TMEMN == @tmemn & TMEMSB1 == @tmemsb1 & TMEMSB2 == @tmemsb2').drop_duplicates(subset= ['SMEMN','TMEMN','TMEMSB1','TMEMSB2'])
# sources =sources.drop_duplicates(subset= ['SMEMN'])



# sources = table.loc[table.duplicated(subset= ['TMEMN','TMEMSB1','TMEMSB2'])]


# for mlno in table['MLNO'].unique():


# schematic.groupby(['SVOL','SVOLNO'])['AFACTR'].sum()
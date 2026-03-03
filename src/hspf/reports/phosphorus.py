# -*- coding: utf-8 -*-
"""
Phosphorous loading calculations — masslink scheme and qualprop transforms.
"""
import pandas as pd


MASSLINK_SCHEME = {'dissolved_orthophosphate': {'tmemn': 'NUIF1',
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
                'labile_oxygen_demand': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':''}}



def qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2 = '',t_code = 4):
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




def dissolved_orthophosphate(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_sand(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_silt(uci,hbn,operation, mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_clay(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def organic_refactory_phosphorous(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def organic_refactory_carbon(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['organic_refactory_carbon']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)
  
def labile_oxygen_demand(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['labile_oxygen_demand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate(uci,hbn,operation,mlno,t_code = 4):
    ts = particulate_orthophosphate_sand(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate_silt(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate_clay(uci,hbn,operation,mlno,t_code)
    return ts


def total_phosphorous(uci,hbn,t_code,operation = 'PERLND'):
    opnids = uci.network.subwatersheds()
    opnids = opnids.loc[opnids['SVOL'] == operation].drop_duplicates(subset = ['SVOLNO','MLNO'])
    
    totals = []
    for mlno in opnids['MLNO'].unique():
        total = dissolved_orthophosphate(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate(uci,hbn,operation,mlno, t_code) + organic_refactory_phosphorous(uci,hbn,operation,mlno,t_code) + labile_oxygen_demand(uci,hbn,operation,mlno,t_code)*0.007326 # Conversation factor to P
        if isinstance(total, (int, float)): #TODO fix for when no data is present. Don't like this workaround.
            pass
        elif not total.empty:
            valid_opnids = total.columns.intersection(opnids['SVOLNO'].loc[opnids['MLNO'] == mlno])
            totals.append(total[valid_opnids])
    
    if len(totals) > 0:
        total = pd.concat(totals,axis=1)
        total = total.T.groupby(total.columns).sum().T
    return total


def subwatershed_total_phosphorous_loading(uci,hbn,reach_ids = None,t_code=5, as_load = True,group_landcover = True):
    tp_loading = total_phosphorous(uci,hbn,t_code)
    if reach_ids is None:
        subwatersheds = uci.network.subwatersheds()
    else:
        subwatersheds = uci.network.subwatersheds(reach_ids)
    
    perlnds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']
    perlnds = perlnds['AFACTR'].groupby([perlnds.index,perlnds['SVOLNO']]).sum().reset_index()
    
    
    total = tp_loading[perlnds['SVOLNO']]
    
    total = total.mul(perlnds['AFACTR'].values,axis=1)       
    
    total = total.transpose()
    total['reach_id'] = perlnds['TVOLNO'].values
    total['landcover'] = uci.table('PERLND','GEN-INFO').loc[total.index,'LSID'].to_list()
    total['area'] = perlnds['AFACTR'].to_list()
    total = total.reset_index().set_index(['index','landcover','area','reach_id']).transpose()
    total.columns.names = ['perlnd_id','landcover','area','reach_id']
    
    if group_landcover:
        total.columns = total.columns.droplevel(['landcover','perlnd_id'])
        total = total.T.reset_index().groupby('reach_id').sum().reset_index().set_index(['reach_id','area']).T
        
    if not as_load:
        total = total.div(total.columns.get_level_values('area').values,axis=1)       

    total.index = pd.to_datetime(total.index)
    return total

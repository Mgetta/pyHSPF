# -*- coding: utf-8 -*-
"""
Created on Mon Dec 23 17:33:46 2024

@author: mfratki
"""

_COLUMN = 'ReachID'
_DS_COLUMN = 'DS_ReachID'

# %% Functions
# First validate that the UCI file opn-sequence block is correct
# Reaches
# Is there an FTABLE?
# Is it a lake reach?
# Is it in the schematic block? Is there any acreage?
# Is it in the ext sources block?
# Is it in the

#%% gis_layer methods

def gis_upstream(reach, gis_layer):
    return gis_layer.loc[gis_layer[_DS_COLUMN] == reach, _COLUMN].to_list()


def gis_downstream(reach, gis_layer):
    return gis_layer.loc[gis_layer[_COLUMN] == reach, _DS_COLUMN].to_list()


def duplicates(gis_layer):
    return gis_layer.loc[gis_layer.duplicated(subset=_COLUMN),_COLUMN].to_list()

def is_duplicate(reach, gis_layer):
    return len(gis_layer.loc[gis_layer[_COLUMN] == reach]) > 1

def is_missing(reach, gis_layer):
    return not any(gis_layer[_COLUMN].isin([reach]))

#%% gis and uci checks

def gis_only(gis_layer, uci):
    return gis_layer.loc[~gis_layer[_COLUMN].isin(uci.valid_opnids['RCHRES']), _COLUMN]

def missing(gis_layer, uci):
    return [reach for reach in uci.valid_opnids['RCHRES'] if is_missing(reach, gis_layer)]


#%% reach specific gis and uci checks


def similar_area(reach,gis_layer,uci,tol = .05):
    uci_area = uci.network.subwatershed_area(reach) 
    gis_area = gis_layer.loc[gis_layer[_COLUMN] == reach].geometry.area*0.000247105 
    
    return abs((uci_area-gis_area)/uci_area) <= tol
    
def test_upstream(reach, gis_layer, uci):
    # Is it a 0 order reach?
    upstream = uci.network.upstream(reach)

    us_pass = False
    if len(upstream) == 0:
        # Make sure the gis layer reach is not in the downstream reach id column
        if not all(gis_layer[_DS_COLUMN] == reach):  # isin([reach])):
            us_pass = True
    else:
        # if any(gis_layer.loc[gis_layer[_DS_COLUMN] == reach,_COLUMN].isin(upstream)):
        if set(gis_layer.loc[gis_layer[_DS_COLUMN] == reach, _COLUMN]) == set(upstream):
            us_pass = True
    return us_pass


def test_downstream(reach, gis_layer, uci):
    # Is it a 0 order reach?
    downstream = uci.network.downstream(reach)

    ds_pass = False
    if len(downstream) == 0:
        if any(gis_layer.loc[gis_layer[_COLUMN] == reach, _DS_COLUMN].isin([999, -999])):
            ds_pass = True
    else:
        if set(gis_layer.loc[gis_layer[_COLUMN] == reach, _DS_COLUMN]) == set(downstream):
            ds_pass = True
    return ds_pass


#%% UCI checks
def same_metzone(reachs, uci):
    '''
    Returns True if all reaches are located within the same metzone, otherwise returns False.
    '''

    return len(uci.opnid_dict['RCHRES'].loc[reachs, 'metzone'].unique()) == 1

def same_metzone(reach_ids,uci):
    dsn = uci.get_dsns('RCHRES',reach_ids[0],'PREC')['SVOLNO'].iloc[0]
    mismatch = [reach_id for reach_id in reach_ids if uci.get_dsns('RCHRES',reach_id,'PREC')['SVOLNO'].iloc[0] != dsn]
    return len(mismatch) == 0


# def validate_subwatershed_metzone(reach,uci):
#     subwatershed = uci.network.subwatershed(reach)
#     reach_dsn = uci.get_dsns('RCHRES',reach,'PREC')
#     subwatershed['dsns'] = pd.concat([uci.get_dsns(row['SVOL'],row['SVOLNO'],'PREC')['SVOLNO'] for index,row in subwatershed.iterrows()]).values


def same_dsns(reach,uci):
    reach_dsn = uci.get_dsns('RCHRES',reach,'PREC')['SVOLNO'].values[0]
    diff = []
    for index,row in uci.network.subwatershed(reach).iterrows():
        perlnd_dsn = uci.get_dsns(row['SVOL'],row['SVOLNO'],'PREC')['SVOLNO'].values[0]
        if perlnd_dsn != reach_dsn:
            diff.append(perlnd_dsn)
    return len(diff) == 0  
            
def has_ftable(reach, uci):
    '''
    Returns True if there is an FTABLE in the uci associated with the reach, otherwise returns False.
    '''
    return f'FTABLE{reach}' in uci.table_names('FTABLES')

def isin_open_sequence(operation,opnid,uci):
    opnseq = uci.table('OPN SEQUENCE')
    return opnid in opnseq.loc[opnseq['OPERATION'] == operation,'SEGMENT'].values

def isin_geninfo(reach, uci):
    return reach in uci.table('RCHRES', 'GEN-INFO').index

def isin_network(reach,uci):
    return reach in uci.network.G.nodes

def isin_schematic(reach, uci):
    schematic = uci.table('SCHEMATIC')
    return reach in set(schematic.loc[schematic['TVOL'] == 'RCHRES','TVOLNO'])
    #return reach in uci.opnid_dict['RCHRES'].index

def svol_isin_schematic(svol,svolnos,uci):
    schematic = uci.table('SCHEMATIC')
    schematic_svolnos = set(schematic.loc[schematic['SVOL'] == svol,'SVOLNO'])
    out = {svolno:svolno in schematic_svolnos for svolno in svolnos}
    if all(out.values()):
        out = True
    return out

def tvol_isin_schematic(tvol,tvolnos,uci):
    schematic = uci.table('SCHEMATIC')
    schematic_tvolnos = set(schematic.loc[schematic['TVOL'] == tvol,'TVOLNO'])
    out = {tvolno:tvolno in schematic_tvolnos for tvolno in tvolnos}
    if all(out.values()):
        out = True
    return out

def number_of_networks(uci):
    return len(uci.network.outlets())

def is_non_contributing_area(reach,uci):
    return all([isin_schematic(reach,uci), not isin_network(reach,uci)])


def isin_uci(reach, uci):
    return reach in uci.valid_opnids['RCHRES']


def has_area(reach, uci):
    subwatersheds = uci.network.subwatersheds()
    return reach in subwatersheds.index

def gets_precip(reach, uci):
    return reach in uci.network.G.nodes

def is_routing_reach(reach, uci):
    #return all([isin_network(reach,uci), not has_area(reach,uci)])
    return uci.network.subwatershed(reach)['AFACTR'].sum() == 0


def is_lake(reach, uci):
    return uci.table('RCHRES', 'GEN-INFO').loc[reach, 'LKFG'] == 1

# def recieves_met(reach,uci):
#     ts_names = ['ATEM','CLOU','DEWP','PEVT','PREC','SOLR','WIND']
#     return reach in set(ext_sources.loc[(ext_sources['TVOL'] == 'RCHRES') & (ext_sources['SMEMN'].isin(ts_names)),'TOPFST'])

#%% In opensequence but not in scehamatic


# for model_name, uci in ucis.items():
#     reach_ids = uci.table('OPN SEQUENCE').query('OPERATION == "RCHRES"')['SEGMENT'].to_list()
#     schem = uci.table('SCHEMATIC')
#     if not all(schem.query('SVOL == "RCHRES"')['SVOLNO'].isin(reach_ids)):
#         print(model_name)


'''
Dummy Terminal Lake (Buffalo)

A reach that acts as a termnial resevoir for upstream inflows. 
No Ftable is needed since there is no routing (but perhaps some include them?)





'''




# opensequence
# ext sources
# schematic
# 

#%%
from dataclasses import dataclass

from hspf.parser.parsers import parseTable
from hspf import warehouse
import duckdb
import pandas as pd
from hspf.uci import UCI
from pathlib import Path
from pyhcal.repository import Repository

#%% Model information
'''
Model
Version (typically deliniated by end year)
Scenario
Run

We have a model for a Basin. Perodically the model is updated and altered enough to be considered a new version. Each version may have multiple scenarios (e.g., different management practices) and each scenario may have multiple runs (e.g., different time periods, different input data).


model: BigFork
version: BigFork_2000_2010
scenario: Base


run_name: Initial Run
run_id: 0
'''


#%% Table Builders

def build_model_table(model_name,uci,version_id=None, scenario_name = 'base',run_id = 0):
    scenario_name = pd.NA
    start_year = int(uci.table('GLOBAL')['start_date'].str[0:4].values[0])
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    if version_id is None:
        version_id = f"{model_name}_{start_year}_{end_year}"

    df_model = pd.DataFrame({
        'model_name': [model_name],
        'version_id': [version_id],
        'run_id': [run_id],
        'start_year': [start_year],
        'end_year': [end_year],
        'scenario_name': [scenario_name]
    })

    return df_model



def build_operations_table(model_name, uci):
    df = uci.table('OPN SEQUENCE')[['OPERATION','SEGMENT']]
    df = df.rename(columns={'SEGMENT': 'operation_id', 'OPERATION': 'operation_type'})
    df['model_name'] = model_name
    return df


def build_schematic_table(model_name, uci):
    df = uci.table('SCHEMATIC')
    df['model_name'] = model_name
    return df

def build_masslink_table(model_name, uci):
    dfs = []
    for table_name in uci.table_names('MASS-LINK'):
        mlno = table_name.split('MASS-LINK')[1]
        masslink = uci.table('MASS-LINK',table_name)
        masslink.insert(0,'MLNO',mlno)
        masslink['model_name'] = model_name
        dfs.append(masslink)
    df = pd.concat(dfs).reset_index(drop=True)
    return df


def build_extsources_table(model_name, uci):
    extsource = uci.table('EXT SOURCES')
    extsource['model_name'] = model_name
    return extsource

def build_exttargets_table(model_name, uci):
    if 'EXT TARGETS' in uci.block_names():
        exttarget = uci.table('EXT TARGETS')
        exttarget['model_name'] = model_name
    else:
        exttarget = pd.DataFrame()
    return exttarget

def build_network_table(model_name, uci):
    if 'NETWORK' in uci.block_names():
        network = uci.table('NETWORK')
        network['model_name'] = model_name
    else:
        network = pd.DataFrame()
    return network

def build_ftables_table(model_name, uci):
    dfs = []
    if 'FTABLES' in uci.block_names():
        for ftable_name in uci.table_names('FTABLES'):
            ftable_num = int(ftable_name.split('FTABLE')[1])
            ftable = uci.table('FTABLES',ftable_name)
            ftable['reach_id'] = ftable_num
            ftable['model_name'] = model_name
            dfs.append(ftable)
    if dfs:
        df = pd.concat(dfs).reset_index(drop=True)
    else:
        df = pd.DataFrame()
    return df


def build_parmeter_table(model_name, uci):
    dfs = []
    for key, value in uci.uci.items():
        if key[0] in ['PERLND','RCHRES','IMPLND']:
            table = uci.table(key[0],key[1],key[2]).reset_index()
            table['model_name'] = model_name
            table['operation_type'] = key[0]
            table['table_name'] = key[1]
            table['table_id'] = key[2]
            table.rename(columns = {'OPNID': 'operation_id'}, inplace=True)
            dfs.append(table.melt(id_vars = ['model_name','table_name','table_id','operation_type','operation_id']))
    df = pd.concat(dfs).reset_index(drop=True)
    return df

#%% Build Tables

#%% Optionally Add PKs

def add_model_pks(models_df):
    models_df['model_pk'] = models_df.index + 1
    return models_df

def add_operation_pks(operations_df, models_df):
    operations_df['operation_pk'] = operations_df.index + 1
    operations_df = operations_df.merge(
        models_df[['model_name', 'model_pk']],
        on='model_name',
        how='left'
    )
    return operations_df

def add_masslink_pks(masslinks_df, models_df):
    mlno_pks = {mlno: idx+1 for idx, mlno in enumerate(masslinks_df[['MLNO','model_name']].drop_duplicates().itertuples(index=False, name=None))}
    masslinks_df['mlno_pk'] = masslinks_df[['MLNO','model_name']].apply(tuple, axis=1).map(mlno_pks)
    return masslinks_df

# Schematics

def add_schematic_pks(schematics_df, operations_df, masslinks_df):
    schematics_df = schematics_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','SVOLNO','SVOL'],
        right_on=['model_name','operation_id','operation_type'],
        how='left'
    ).rename(columns={'operation_pk': 'source_operation_pk'})

    schematics_df = schematics_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','TVOL','TVOLNO'],
        right_on=['model_name','operation_type','operation_id'],
        how='left'
    ).rename(columns={'operation_pk': 'target_operation_pk'})
    #Join masslink pks
    schematics_df = schematics_df.merge(
        masslinks_df[['model_name','MLNO','mlno_pk']],
        on=['model_name','MLNO'],
        how='left'
    )
    #set operatin_pk dtyes to int
    schematics_df['source_operation_pk'] = schematics_df['source_operation_pk'].astype('Int64')
    schematics_df['target_operation_pk'] = schematics_df['target_operation_pk'].astype('Int64')
    schematics_df[['source_operation_pk','target_operation_pk','AFACTR','MLNO','TMEMSB1','TMEMSB2']]
    schematics_df['mlno_pk'] = schematics_df['mlno_pk'].astype('Int64')
    return schematics_df

#% Ext Sources
def add_extsource_pks(extsources_df, operations_df):
    extsources_df = extsources_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','TVOL','TOPFST'],
        right_on=['model_name','operation_type','operation_id'],
        how='left'
    ).rename(columns={'operation_pk': 'target_operation_pk'})
    return extsources_df
#% Ext Targets
def add_exttarget_pks(exttargets_df, operations_df):
    exttargets_df = exttargets_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','SVOL','SVOLNO'],
        right_on=['model_name','operation_type','operation_id'],
        how='left'
    ).rename(columns={'operation_pk': 'source_operation_pk'})
    return exttargets_df
#% Network
def add_network_pks(networks_df, operations_df):
    networks_df = networks_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','TOPFST','TVOL'],
        right_on=['model_name','operation_id','operation_type'],
        how='left'
    ).rename(columns={'operation_pk': 'target_operation_pk'})
    networks_df = networks_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']],
        left_on=['model_name','SVOL','SVOLNO'],
        right_on=['model_name','operation_type','operation_id'],
        how='left'
    ).rename(columns={'operation_pk': 'source_operation_pk'})
    return networks_df
#% FTABLES
def add_ftable_pks(ftables_df, operations_df):
    ftables_df = ftables_df.merge(
        operations_df[['model_name','operation_id','operation_type','operation_pk']].query('operation_type == "RCHRES"'),
        left_on=['model_name','reach_id'],
        right_on=['model_name','operation_id'],
        how='left'
    ).rename(columns={'operation_pk': 'ftable_operation_pk'})
    return ftables_df
#% Parameters, Flags, Properties
def add_param_pks(params, operations_df, models_df):
    params = params.merge(models_df[['model_name','model_pk']], on='model_name', how='left')
    params = params.merge(operations_df[['model_name','operation_id','operation_type','operation_pk']],
                        left_on=['model_name','operation_id','operation_type'],
                        right_on=['model_name','operation_id','operation_type'],
                        how='left')
    return params

def add_flag_pks(flags, operations_df, models_df):
    flags = flags.merge(models_df[['model_name','model_pk']], on='model_name', how='left')
    flags = flags.merge(operations_df[['model_name','operation_id','operation_type','operation_pk']],
                        left_on=['model_name','operation_id','operation_type'],
                        right_on=['model_name','operation_id','operation_type'],
                        how='left')
    return flags

def add_prop_pks(props, operations_df, models_df):
    props = props.merge(models_df[['model_name','model_pk']], on='model_name', how='left')
    props = props.merge(operations_df[['model_name','operation_id','operation_type','operation_pk']],
                        left_on=['model_name','operation_id','operation_type'],
                        right_on=['model_name','operation_id','operation_type'],
                        how='left')
    return props




#Dump all dataframes to warehouse
#%% Dump to Warehouse
def load_to_warehouse(db_path,model_names = None,replace=True):
    if model_names is None:
        model_names = Repository.valid_models()
    ucis = {model_name: UCI(Repository(model_name).uci_file,True) for model_name in model_names}
    models_df = pd.concat([build_model_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    operations_df = pd.concat([build_operations_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    masslinks_df = pd.concat([build_masslink_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    schematics_df = pd.concat([build_schematic_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True) 
    extsources_df = pd.concat([build_extsources_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    exttargets_df = pd.concat([build_exttargets_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    networks_df = pd.concat([build_network_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    ftables_df = pd.concat([build_ftables_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    df = pd.concat([build_parmeter_table(model_name, uci) for model_name, uci in ucis.items()]).reset_index(drop=True)
    df = pd.merge(df,parseTable,left_on = ['operation_type','table_name','variable'],
            right_on = ['block','table2','column'],how='left')[['model_name','operation_type','table_name','table_id','operation_id','variable','value','dtype']]
    props = df.query('dtype == "C"')
    flags = df.query('dtype == "I"')
    params = df.query('dtype == "R"')

    with duckdb.connect(db_path) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS hspf")

        warehouse.load_df_to_table(con, models_df, 'models',replace)
        warehouse.load_df_to_table(con, operations_df, 'operations',replace)
        warehouse.load_df_to_table(con, schematics_df, 'schematics',replace)
        warehouse.load_df_to_table(con, masslinks_df, 'masslinks',replace)
        warehouse.load_df_to_table(con, extsources_df, 'extsources',replace)
        warehouse.load_df_to_table(con, exttargets_df, 'exttargets',replace)
        warehouse.load_df_to_table(con, networks_df, 'networks',replace)
        warehouse.load_df_to_table(con, ftables_df, 'ftables',replace)
        warehouse.load_df_to_table(con, props, 'properties',replace)
        warehouse.load_df_to_table(con, flags, 'flags',replace)
        warehouse.load_df_to_table(con, params, 'parameters',replace)

#%% Catchment Constituent Loadings

def catchment_loadings(model_name, mod):
        dfs = []
        for constituent in ['Q','TSS','N','TKN','TP','OP']:
            df_constituent = mod.reports.catchment_loading(constituent,True)
            dfs.append(df_constituent)
        df = pd.concat(dfs)
        df['model_name'] = model_name
        df['month'] = df['datetime'].dt.month
        df['year'] = df['datetime'].dt.year
        return df






#%% Model Scour Reports



#%% Outlet Contributions




#%%

db_path = 'c:/Users/mfratki/Documents/hspf.duckdb'



#%% HBN Output Exploration

with duckdb.connect(db_path) as con:
    warehouse.create_model_run_table(con)



model_name = 'BigFork'
run_id = 1

run_id = 47


hbn = cal.model.hbns
mapn = hbn.hbns[0].mapn

outputs = hbn.hbns[0].output_dictionary
dfs = []
for key,ts_names in outputs.items():
    keys = key.split('_')
    operation = keys[0]
    activity = keys[1]
    opnid = int(keys[2])
    t_code = keys[3]
    df = pd.DataFrame({'operation': operation,
                  'activity': activity,
                  'opnid': opnid,
                  't_code': t_code,
                  'ts_names': ts_names})
    dfs.append(df)
output_df = pd.concat(dfs).reset_index(drop=True)

dfs = []
for key,data in hbn.hbns[0].data_frames.items():
    keys = key.split('_')
    operation = keys[0]
    activity = keys[1]
    opnid = int(keys[2])
    t_code = keys[3]
    data.reset_index(inplace=True)
    data.rename(columns={'index': 'datetime'}, inplace=True)
    data = data.melt(id_vars = ['datetime'],var_name = 'ts_name', value_name = 'value')
    data['operation'] = operation
    data['activity'] = activity
    data['opnid'] = opnid
    data['t_code'] = t_code
    data['model_name'] = model_name
    dfs.append(data)
output_df = pd.concat(dfs).reset_index(drop=True)



# Write to Parquet with DuckDB, including "t_code" as a partition
output_path = "model_outputs"

con = duckdb.connect(database=':memory:')  # Temporary in-memory database
con.execute(f"""
    COPY output_df
    TO '{output_path}'
    (FORMAT 'parquet', PARTITION_BY ('model_name','operation', 'opnid'))
""")

print(f"Data written to {output_path}")



['PERO',
'SURO',
'IFWO',
'AGWO']

for constituent in ['Q','TSS','TP','N','OP','BOD','TKN']:
    t_cons = helpers.get_tcons(constituent,'RCHRES','lb')
    df = hbn.get_rechres_data(constituent, units='lb', freq='daily').reset_index()


pero = hbn.get_multiple_timeseries(op_type,t_code,ts_name).reset_index().rename(columns={'index': 'datetime'})
pero = pero.melt(id_vars = ['datetime'],var_name = 'operation_id', value_name = 'value')
pero['ts_name'] = ts_name
pero['t_code'] = t_code
pero['model_name'] = model_name


db_path = 'c:/Users/mfratki/Documents/ucis.duckdb'
with duckdb.connect(db_path) as con:
    warehouse.insert_model_run(con, model_name, run_id)

db_path = 'c:/Users/mfratki/Documents/ucis.duckdb'
with duckdb.connect(db_path) as conn:
    conn.execute("CREATE SCHEMA if not exists reports")
    conn.execute("CREATE TABLE if not exists reports.catchment_loading AS SELECT * FROM df")
    conn.close()


# Average annual loading by catchment 
db_path = 'c:/Users/mfratki/Documents/ucis.duckdb'
with duckdb.connect(db_path) as conn:
    query = f"""
    SELECT 
        model_name,
        operation AS operation_type,
        opnid AS operation_id,
        t_code,
        ts_name AS constituent,
        AVG(value) * 365.25 AS annual_loading
    FROM reports.catchment_loading
    WHERE t_code = 'PERLND' AND constituent IN ('Q','TP','TSS','N','OP','BOD','TKN')
    GROUP BY model_name, TVOLNO, constituent
    """
    annual_loadings = conn.execute(query).fetchdf()
    conn.close()

hbn.hbns[0].data_frames.keys()



import duckdb
import pandas as pd


# Convert to DataFrame
df = pd.DataFrame(data)
df['datetime'] = pd.to_datetime(df['datetime'])  # Ensure datetime column is formatted properly

# Write to Parquet with DuckDB, including "t_code" as a partition
output_path = "model_outputs"

con = duckdb.connect(database=':memory:')  # Temporary in-memory database
con.execute(f"""
    COPY df
    TO '{output_path}'
    (FORMAT 'parquet', PARTITION_BY ('operation_type', 'operation_id', 't_code'))
""")

print(f"Data written to {output_path}")






#%% Catchments
def build_catchments_table(model_name, uci):
    df = pd.DataFrame({'catchment_id': uci.network.catchment_ids})
    df['catchment_name'] = pd.NA
    df['model_name'] = model_name
    return df

catchments = []
for model_name, uci in ucis.items():
    df = build_catchments_table(model_name, uci)
    catchments.append(df)
catchments_df = pd.concat(catchments).reset_index(drop=True)
catchments_df['catchment_pk'] = catchments_df.index + 1


#%% Catchment Operations
catchment_operations = []
# for model_name, uci in ucis.items():
#     dfs = []
#     for reach_id in uci.network.get_node_type_ids('RCHRES'):
#         df = uci.network.drainage(reach_id)
#         df['catchment_id'] = reach_id
#         dfs.append(df)
#     df = pd.concat(dfs).reset_index(drop=True)
#     df['model_name'] = model_name
#     catchment_operations.append(df)
# catchment_operations_df = pd.concat(catchment_operations).reset_index(drop=True)
# catchment_operations_df.rename(columns = {
#                          'source_type_id': 'source_operation_id',
#                          'source_type': 'source_operation'}, inplace=True)

for model_name, uci in ucis.items():
    df = uci.network.subwatersheds().reset_index()
    df['model_name'] = model_name
    df.rename(columns = {'TVOLNO': 'catchment_id',
                         'SVOLNO': 'source_operation_id',
                         'SVOL': 'source_operation',
                         'MLNO': 'mlno',
                         'AFACTR': 'area'}, inplace=True)
    catchment_operations.append(df)
catchment_operations_df = pd.concat(catchment_operations).reset_index(drop=True)


#%% Join Model PKs
operations_df = operations_df.merge(models_df[['model_name','model_pk']], on='model_name', how='left')
catchments_df = catchments_df.merge(models_df[['model_name','model_pk']], on='model_name', how='left')
catchment_operations_df = catchment_operations_df.merge(models_df[['model_name','model_pk']], on='model_name', how='left')

#%% Join catchment pks
catchment_operations_df = catchment_operations_df.merge(
    catchments_df[['model_pk','catchment_id','catchment_pk']],
    on=['model_pk','catchment_id'],
    how='left'
)

cathcment_operations_df = catchment_operations_df.merge(
    operations_df[['model_pk','operation_id','operation_type','operation_pk']],
    left_on=['model_pk','source_operation_id','source_operation'],
    right_on=['model_pk','operation_id','operation_type'],
    how='left'
).rename(columns={'operation_pk': 'source_operation_pk'})

catchment_operations_df = catchment_operations_df.merge(
    operations_df[['model_pk','operation_id','operation_type','operation_pk']],
    left_on=['model_pk','target_operation_id','target_operation'],
    right_on=['model_pk','operation_id','operation_type'],
    how='left'
).rename(columns={'operation_pk': 'target_operation_pk'})



#%% Properties, Flags, Parameters
# duplicate_tables = []
# for model_name, uci in ucis.items():
#     for key, value in uci.uci.items():
#         if key[0] in ['PERLND','RCHRES','IMPLND']:
#             if key[2] > 0:
#                 duplicate_tables.append(key)


# Special Tables
'''
IMPLND QUAL-INPUT 0, 1, 2, 3, 4`: 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM
IMPLND QUAL-PROPS 0, 1, 2, 3, 4 : 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM
PERLND MON-ACCUM 0, 1, 2 : 0 = ?, 1= ?, 2 = ?
PERLND MON-GRND-CONC 0,1,2,3,4,5 : 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM, 5= TSS
PERLND MON-IFLW-CONC 0,1,2,3,4 : 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM
PERLND MON-POTFW 0,1 : 0 = ?, 1 = ?
PERLND MON-SQOLIM 0,1 : 0 = ?, 1 = ?
PERLND QUAL-INPUT 0,1,2,3,5 : 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM, 5= TSS
PERLND QUAL-PROPS 0,1,2,3,5 : 0 = NH3+NH4, 1=NO3, 2 = ORTHO P, 3= BOD, 4 = F.COLIFORM, 5= TSS
RCHRES SILT-CLAY-PM 0,1 : 0 = SILT, 1 = CLAY
'''
#props = parseTable.query('dtype == "C"').query('column != "OPNID"')



#%%
dfs = {key: pd.concat(value) for key, value in dfs.items()}    

for row in props.iterrows():
    if row['table2'] in uci.table_names(row['block']):
        df_prop = uci.table(row['block'],row['table2'])[['OPNID',row['column']]]
        df = df.rename(columns={row['column']: 'value'})
        df['property_name'] = row['column']
        df['model_name'] = model_name
        properties.append(df)




#%%







for model_name, uci in ucis.items():
    extsources = uci.table('EXT SOURCES')
    extsources['SVOL'] = extsources['SVOL'].str.upper().replace({'WDM': 'WDM1'})

    files = uci.table('FILES')
    files['FTYPE'] = files['FTYPE'].str.upper().replace({'WDM': 'WDM1'})

    df = pd.merge(extsources,files,how='left',left_on = 'SVOL',right_on = 'FTYPE')
    if 'EXT TARGETS' in uci.block_names():
        extargets = uci.table('EXT TARGETS')
        extargets['model_name'] = model_name
        extargets['SVOL'] = extargets['SVOL'].str.upper().replace({'WDM': 'WDM1'})

        df2 = pd.merge(extargets,files,how='left',left_on = 'SVOL',right_on = 'FTYPE')


catchment_operations.append(df)


# Properties
parseTable.query('dtype == "C"')


# Parameters
#%% PERLND Hydrology Parameters
 # [Table-type PWAT-PARM1]
 #  Table-type PWAT-PARM2
 # [Table-type PWAT-PARM3]
 #  Table-type PWAT-PARM4
 # [Table-type PWAT-PARM5]
 # [Table-type PWAT-PARM6]
 # [Table-type PWAT-PARM7]


table_names = ['PWAT-PARM2','PWAT-PARM3','PWAT-PARM4','PWAT-PARM5']




dfs = []
for model_name, uci in ucis.items():
    model_pk = Models.find(model_name)[0] 
    table_names = ['PWAT-PARM2','PWAT-PARM3','PWAT-PARM4','PWAT-PARM5']
    params = [uci.table('PERLND',table_name) for table_name in table_names if table_name in uci.table_names('PERLND')]
    merged_df = params[0]
    for df in params[1:]:
        merged_df = merged_df.join(df)
    df = merged_df.stack().reset_index()
    df.columns = ['OPNID','name','value']
    df.insert(0,'OPERATION','PERLND')
    df.insert(0,'model_pk',model_pk)
    dfs.append(df)
params = pd.concat(dfs)
# Flags
flags = parseTable.query('dtype == "I"')




df[['TGRPN', 'TMEMN', 'TMEMSB1_y','TMEMSB2_y']].drop_duplicates().shape
df[['SGRPN', 'SMEMN', 'SMEMSB1','SMEMSB2']].drop_duplicates().shape

df[['TGRPN', 'TMEMN', 'TMEMSB1_y','TMEMSB2_y']].drop_duplicates()

for masslink in masslinks:
    for mlno in masslink['MLNO'].unique():
        if len(masslink.query(f'MLNO == "{mlno}"')['TVOL'].unique()) > 1:
            print(f"{masslink['model_name'].iloc[0]} MASS-LINK{mlno} has multiple TVOL entries.")


for mlno in schematic['MLNO'].unique():
    svol = schematic.query(f'MLNO == "{mlno}"')['SVOL'].unique()
    tvol = schematic.query(f'MLNO == "{mlno}"')['TVOL'].unique()

df_targets = []  
df_extsources = []        
for model_name, uci in ucis.items():
    files = uci.table('FILES')
    files['FTYPE'] = files['FTYPE'].str.upper().replace({'WDM': 'WDM1'})
    extsources = uci.table('EXT SOURCES')
    extsources['SVOL'] = extsources['SVOL'].str.upper().replace({'WDM': 'WDM1'})
    extsources['model_name'] = model_name
    df_extsources.append(pd.merge(extsources,files,how='left',left_on = 'SVOL',right_on = 'FTYPE'))
    if 'EXT TARGETS' in uci.block_names():
        extargets = uci.table('EXT TARGETS')
        extargets['model_name'] = model_name
        extargets['TVOL'] = extargets['TVOL'].str.upper().replace({'WDM': 'WDM1'})
        df = pd.merge(extargets,files,how='left',left_on = 'TVOL',right_on = 'FTYPE')
        df_targets.append(df)

df_targets = pd.concat(df_targets,ignore_index=True)
df_extsources = pd.concat(df_extsources,ignore_index=True)  


df_targets.rename(columns = {'TVOLNO': 'dsn',
                     'SVOL': 'operation',
                     'SVOLNO': 'operation_id'}, inplace=True)

df_extsources.rename(columns = {'SVOLNO': 'dsn',
                     'TVOL': 'operation',
                     'TVOLNO': 'operation_id'}, inplace=True)

df = pd.merge(df_targets,df_extsources,how='inner',left_on = ['FILENAME','dsn'],right_on = ['FILENAME','dsn'],suffixes=('_source','_target'))
df[['operation_source','operation_id','model_name_source','operation_target','TOPFST','model_name_target','FILENAME']].drop_duplicates()



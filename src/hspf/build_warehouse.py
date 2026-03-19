from hspf import hspfModel, reports, uci
from hspf.parser.parsers import parseTable
from hspf import warehouse
import duckdb
import pandas as pd
from hspf.uci import UCI
from pathlib import Path


# ---------------------------------------------------------------------------
# Table Builders
# ---------------------------------------------------------------------------

def build_model_table(model_name, uci, run_id='base', notes=None):
    start_year = int(uci.table('GLOBAL')['start_date'].str[0:4].values[0])
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    df_model = pd.DataFrame({
        'model_name': [model_name],
        'model_year': [end_year],
        'run_id': [run_id],
        'start_year': [start_year],
        'notes': [notes],
    })

    return df_model


def build_operations_table(model_name, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    df = uci.table('OPN SEQUENCE')[['OPERATION', 'SEGMENT']]
    df = df.rename(columns={'SEGMENT': 'operation_id', 'OPERATION': 'operation_type'})
    df['model_name'] = model_name
    df['model_year'] = end_year

    df_metzones = pd.concat(uci.get_metzones()).reset_index()
    df = pd.merge(df, df_metzones, right_on=['level_0', 'TOPFST'],
                  left_on=['operation_type', 'operation_id'], how='left')
    df = df[['model_name', 'model_year', 'operation_type', 'operation_id', 'metzone']]
    return df


def build_schematic_table(model_name, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    df = uci.table('SCHEMATIC')
    df['model_name'] = model_name
    df['model_year'] = end_year
    return df


def build_masslink_table(model_name, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    dfs = []
    for table_name in uci.table_names('MASS-LINK'):
        mlno = table_name.split('MASS-LINK')[1]
        masslink = uci.table('MASS-LINK', table_name)
        masslink.insert(0, 'MLNO', mlno)
        masslink['model_name'] = model_name
        masslink['model_year'] = end_year
        dfs.append(masslink)
    df = pd.concat(dfs).reset_index(drop=True)
    return df


def build_ftables_table(model_name, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    dfs = []
    if 'FTABLES' in uci.block_names():
        for ftable_name in uci.table_names('FTABLES'):
            ftable_num = int(ftable_name.split('FTABLE')[1])
            ftable = uci.table('FTABLES', ftable_name)
            ftable['reach_id'] = ftable_num
            ftable['model_name'] = model_name
            ftable['model_year'] = end_year
            dfs.append(ftable)
    if dfs:
        df = pd.concat(dfs).reset_index(drop=True)
        # Normalize column names to match schema: depth, area, volume, discharge
        col_map = {col: col.lower() for col in df.columns
                   if col.lower() in ('depth', 'area', 'volume', 'discharge')}
        df = df.rename(columns=col_map)
        df = df[['model_name', 'model_year', 'reach_id'] +
                [c for c in ['depth', 'area', 'volume', 'discharge'] if c in df.columns]]
    else:
        df = pd.DataFrame()
    return df


def build_parameter_table(model_name, uci, run_id='base'):
    """
    Build denormalized parameter, flag, and property tables for a model run.
    Returns a dict with keys 'parameters', 'flags', 'properties', each a DataFrame.
    """
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    dfs = []
    for key, value in uci.uci.items():
        if key[0] in ['PERLND', 'RCHRES', 'IMPLND']:
            table = uci.table(key[0], key[1], key[2]).reset_index()
            table['model_name'] = model_name
            table['model_year'] = end_year
            table['run_id'] = run_id
            table['operation_type'] = key[0]
            table['table_name'] = key[1]
            table['table_id'] = key[2]
            table.rename(columns={'OPNID': 'operation_id'}, inplace=True)
            dfs.append(table.melt(
                id_vars=['model_name', 'model_year', 'run_id', 'table_name', 'table_id',
                         'operation_type', 'operation_id']
            ))
    df = pd.concat(dfs).reset_index(drop=True)
    df = pd.merge(
        df, parseTable,
        left_on=['operation_type', 'table_name', 'variable'],
        right_on=['block', 'table2', 'column'],
        how='left'
    )[['model_name', 'model_year', 'run_id', 'operation_type', 'table_name',
       'table_id', 'operation_id', 'variable', 'value', 'dtype']]

    params = df.query('dtype == "R"').copy()
    params = params.rename(columns={'variable': 'parameter_name', 'value': 'parameter_value'})
    params['parameter_value'] = pd.to_numeric(params['parameter_value'], errors='coerce')
    params = params[['model_name', 'model_year', 'run_id', 'operation_type', 'operation_id',
                     'table_name', 'parameter_name', 'parameter_value']]

    flags = df.query('dtype == "I"').copy()
    flags = flags.rename(columns={'variable': 'flag_name', 'value': 'flag_value'})
    flags['flag_value'] = pd.to_numeric(flags['flag_value'], errors='coerce').astype('Int64')
    flags = flags[['model_name', 'model_year', 'run_id', 'operation_type', 'operation_id',
                   'table_name', 'flag_name', 'flag_value']]

    props = df.query('dtype == "C"').copy()
    props = props.rename(columns={'variable': 'property_name', 'value': 'property_value'})
    props['property_value'] = props['property_value'].astype(str)
    props = props[['model_name', 'model_year', 'run_id', 'operation_type', 'operation_id',
                   'table_name', 'property_name', 'property_value']]

    return {'parameters': params, 'flags': flags, 'properties': props}


# ---------------------------------------------------------------------------
# Load / Add orchestration
# ---------------------------------------------------------------------------

def load_model(con, model_name, uci, run_id='base'):
    """Load a single model's UCI data into the warehouse, replacing existing data."""
    df_model = build_model_table(model_name, uci, run_id=run_id)
    df_operations = build_operations_table(model_name, uci)
    df_masslinks = build_masslink_table(model_name, uci)
    df_schematics = build_schematic_table(model_name, uci)
    df_ftables = build_ftables_table(model_name, uci)
    param_tables = build_parameter_table(model_name, uci, run_id=run_id)

    warehouse.load_df_to_table(con, df_model, 'models', replace=True)
    warehouse.load_df_to_table(con, df_operations, 'uci.operations', replace=True)
    warehouse.load_df_to_table(con, df_schematics, 'uci.schematics', replace=True)
    warehouse.load_df_to_table(con, df_masslinks, 'uci.masslinks', replace=True)
    warehouse.load_df_to_table(con, df_ftables, 'uci.ftables', replace=True)
    warehouse.load_df_to_table(con, param_tables['properties'], 'uci.properties', replace=True)
    warehouse.load_df_to_table(con, param_tables['flags'], 'uci.flags', replace=True)
    warehouse.load_df_to_table(con, param_tables['parameters'], 'uci.parameters', replace=True)


def add_model(con, model_name, uci, run_id='base'):
    """Append a single model's UCI data into the warehouse."""
    df_model = build_model_table(model_name, uci, run_id=run_id)
    df_operations = build_operations_table(model_name, uci)
    df_masslinks = build_masslink_table(model_name, uci)
    df_schematics = build_schematic_table(model_name, uci)
    df_ftables = build_ftables_table(model_name, uci)
    param_tables = build_parameter_table(model_name, uci, run_id=run_id)

    warehouse.add_df_to_table(con, df_model, 'main', 'models')
    warehouse.add_df_to_table(con, df_operations, 'uci', 'operations')
    warehouse.add_df_to_table(con, df_schematics, 'uci', 'schematics')
    warehouse.add_df_to_table(con, df_masslinks, 'uci', 'masslinks')
    warehouse.add_df_to_table(con, df_ftables, 'uci', 'ftables')
    warehouse.add_df_to_table(con, param_tables['properties'], 'uci', 'properties')
    warehouse.add_df_to_table(con, param_tables['flags'], 'uci', 'flags')
    warehouse.add_df_to_table(con, param_tables['parameters'], 'uci', 'parameters')


def load_to_warehouse(db_path, model_names=None, run_id='base', replace=True):
    """
    Load UCI data for multiple models into the warehouse.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB database file.
    model_names : list, optional
        List of model names to load. If None, loads all valid models.
    run_id : str
        Run identifier, defaults to 'base'.
    replace : bool
        If True, replaces existing tables; if False, appends.
    """
    from pyhcal.repository import Repository

    if model_names is None:
        model_names = Repository.valid_models()

    print("Loading UCIs into memory...")
    ucis = {model_name: UCI(Repository(model_name).uci_file, True) for model_name in model_names}
    print("UCIs loaded. Building tables...")

    models_df = pd.concat(
        [build_model_table(n, u, run_id=run_id) for n, u in ucis.items()]
    ).reset_index(drop=True)

    operations_df = pd.concat(
        [build_operations_table(n, u) for n, u in ucis.items()]
    ).reset_index(drop=True)

    masslinks_df = pd.concat(
        [build_masslink_table(n, u) for n, u in ucis.items()]
    ).reset_index(drop=True)

    schematics_df = pd.concat(
        [build_schematic_table(n, u) for n, u in ucis.items()]
    ).reset_index(drop=True)

    ftables_df = pd.concat(
        [build_ftables_table(n, u) for n, u in ucis.items()]
    ).reset_index(drop=True)

    param_parts = [build_parameter_table(n, u, run_id=run_id) for n, u in ucis.items()]
    params_df = pd.concat([p['parameters'] for p in param_parts]).reset_index(drop=True)
    flags_df = pd.concat([p['flags'] for p in param_parts]).reset_index(drop=True)
    props_df = pd.concat([p['properties'] for p in param_parts]).reset_index(drop=True)

    print("Tables built. Loading to warehouse...")
    with duckdb.connect(db_path) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS uci")
        con.execute("CREATE SCHEMA IF NOT EXISTS output")
        con.execute("CREATE SCHEMA IF NOT EXISTS reports")

        warehouse.load_df_to_table(con, models_df, 'models', replace)
        warehouse.load_df_to_table(con, operations_df, 'uci.operations', replace)
        warehouse.load_df_to_table(con, schematics_df, 'uci.schematics', replace)
        warehouse.load_df_to_table(con, masslinks_df, 'uci.masslinks', replace)
        warehouse.load_df_to_table(con, ftables_df, 'uci.ftables', replace)
        warehouse.load_df_to_table(con, props_df, 'uci.properties', replace)
        warehouse.load_df_to_table(con, flags_df, 'uci.flags', replace)
        warehouse.load_df_to_table(con, params_df, 'uci.parameters', replace)
    print("Data loaded to warehouse.")


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def build_catchment_loading_table(model_name, uci, hbn, run_id='base'):
    """
    Build the catchment loading report table for a model run.
    """
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])
    dfs = []
    for constituent in ['Q', 'TSS', 'N', 'OP', 'TP', 'TKN']:
        df = reports.catchment_loading_summary(uci, hbn, constituent)
        df['constituent'] = constituent
        df['model_name'] = model_name
        df['model_year'] = end_year
        df['run_id'] = run_id
        dfs.append(df)
    return pd.concat(dfs)

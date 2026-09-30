from typing import Iterable

from hspf import reports
from hspf.core.errors import ConventionError
from hspf.lake.catalogs.io import (
    append_catalog_rows,
    read_catalog_table as _read_catalog_table,
    write_catalog_table as _write_catalog_table,
)
from hspf.lake.layout import LakeLayout
from hspf.model.parsers import parseTable
from hspf.lake import warehouse
import pandas as pd
from pathlib import Path

# Adding the raw uci catalogs
# ---------------------------------------------------------------------------
# Table Builders
# ---------------------------------------------------------------------------

def build_files_table(run_id, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])
    df = uci.table('FILES')
    df['FTYPE'] = df['FTYPE'].str.upper().replace({'WDM': 'WDM1'})
    df['run_id'] = run_id

def build_operations_table(run_id, uci):
    end_year = int(uci.table('GLOBAL')['end_date'].str[0:4].values[0])

    df = uci.table('OPN SEQUENCE')[['OPERATION', 'SEGMENT']]
    df = df.rename(columns={'SEGMENT': 'operation_id', 'OPERATION': 'operation_type'})
    df['run_id'] = run_id
    return df


def build_schematic_table(run_id, uci):
    df = uci.table('SCHEMATIC')
    df['run_id'] = run_id
    return df


def build_masslink_table(run_id, uci):
    dfs = []
    for table_name in uci.table_names('MASS-LINK'):
        mlno = table_name.split('MASS-LINK')[1]
        masslink = uci.table('MASS-LINK', table_name)
        masslink.insert(0, 'MLNO', mlno)
        masslink['run_id'] = run_id
        dfs.append(masslink)
    df = pd.concat(dfs).reset_index(drop=True)
    df['run_id'] = run_id
    return df

def build_extsources_table(run_id, uci):

    extsource = uci.table('EXT SOURCES')
    extsource['SVOL'] = extsource['SVOL'].str.upper().replace({'WDM': 'WDM1'})

    extsource['run_id'] = run_id
    return extsource


def build_exttargets_table(run_id, uci):
    if 'EXT TARGETS' in uci.block_names():
        exttarget = uci.table('EXT TARGETS')
        exttarget['SVOL'] = exttarget['SVOL'].str.upper().replace({'WDM': 'WDM1'})
        exttarget['run_id'] = run_id
    else:
        exttarget = pd.DataFrame()
    return exttarget


def build_network_table(run_id, uci):

    if 'NETWORK' in uci.block_names():
        network = uci.table('NETWORK')
        network['run_id'] = run_id
    else:
        network = pd.DataFrame()
    return network
 
def build_gener_table(run_id, uci):
    table_names = set(uci.table_names('GENER'))
    if len(table_names) > 0:
        # ORDER of tables is important, start with OPCODE
        df = uci.table('GENER','OPCODE')
        table_names.remove('OPCODE')
        for table_name in table_names:
            df = df.join(uci.table('GENER',table_name))
        df['run_id'] = run_id
    else:
        df = pd.DataFrame()
    return df


def build_ftables_table(run_id, uci):
    dfs = []
    for ftable_name in uci.table_names('FTABLES'):
        ftable_num = int(ftable_name.split('FTABLE')[1])
        ftable = uci.table('FTABLES', ftable_name)
        ftable['reach_id'] = ftable_num
        ftable['run_id'] = run_id
        dfs.append(ftable)

    df = pd.concat(dfs).reset_index(drop=True)
    return df


def build_parameter_table(run_id, uci,operation,table_name,table_id):
    """
    Build denormalized parameter, flag, and property tables for a model run.
    Returns a dict with keys 'parameters', 'flags', 'properties', each a DataFrame.
    """
    
    table = uci.table(operation, table_name, table_id).reset_index()
    table['run_id'] = run_id
    table['block'] = operation
    table['table_name'] = table_name
    table['table_id'] = table_id

    return table

def build_parameter_tables(run_id, uci):
    tables = {}
    for key in uci.uci.keys():
        if key[0] in ['PERLND','IMPLND','RCHRES']:
            operation = key[0]
            table_name = key[1]
            table_id = key[2]
            table = build_parameter_table(run_id, uci, operation, table_name, table_id)
            tables[f'{operation}_{table_name}_{table_id}'] = table
    return tables


def add_model(layout, run_id, uci,replace_existing=False):
    """Append a single model's UCI data into the warehouse."""
    df_files = build_files_table(run_id, uci)
    df_operations = build_operations_table(run_id, uci)
    df_masslinks = build_masslink_table(run_id, uci)
    df_schematics = build_schematic_table(run_id, uci)
    df_extsources = build_extsources_table(run_id, uci)
    df_exttargets = build_exttargets_table(run_id, uci)
    df_networks = build_network_table(run_id, uci)
    df_ftables = build_ftables_table(run_id, uci)



    append_frame_to_catalog(layout,run_id, 'models', df_files, replace_existing=replace_existing)
    append_frame_to_catalog(layout,run_id, 'operations', df_operations, replace_existing=replace_existing)
    append_frame_to_catalog(layout,run_id, 'schematics', df_schematics, replace_existing=replace_existing)
    append_frame_to_catalog(layout,run_id, 'masslinks', df_masslinks, replace_existing=replace_existing)
    append_frame_to_catalog(layout,run_id, 'extsources', df_extsources, replace_existing=replace_existing)
    if not df_exttargets.empty:
        append_frame_to_catalog(layout,run_id, 'exttargets', df_exttargets, replace_existing=replace_existing)
    if not df_networks.empty:
        append_frame_to_catalog(layout,run_id, 'networks', df_networks, replace_existing=replace_existing)
    append_frame_to_catalog(layout,run_id, 'ftables', df_ftables, replace_existing=replace_existing)
    param_tables = build_parameter_tables(run_id, uci)
    for key, table in param_tables.items():
        append_frame_to_catalog(layout, run_id, key, table, replace_existing=replace_existing)

def append_frame_to_catalog(
    layout: LakeLayout,
    run_id: str,
    catalog_name: str,
    record: Iterable | pd.DataFrame,
    *,
    replace_existing: bool = False,
) -> Path:
    """Append one run record to ``catalog/runs.parquet``."""

    return append_catalog_rows(
        layout,
        catalog_name,
        record,
        tuple(record.columns) if isinstance(record, pd.DataFrame) else (),
        subdir="uci",
        replace_existing=replace_existing,
        label=catalog_name,
    )

def read_catalog_table(layout: LakeLayout, catalog_name: str, subdir: str | None = None) -> pd.DataFrame:
    """Read a catalog table from the UCI subdirectory."""
    return _read_catalog_table(layout, catalog_name, subdir=subdir, missing="raise")

def _to_frame(record: Iterable | pd.DataFrame) -> pd.DataFrame:
    if isinstance(record, pd.DataFrame):
        return record
    return pd.DataFrame(record)

def write_frame_to_catalog(
    layout: LakeLayout,
    records: Iterable | pd.DataFrame,
    catalog_name: str,
    overwrite: bool = True,
) -> Path:
    """Write ``catalog/edges.parquet``."""

    return _write_catalog_table(
        layout,
        catalog_name,
        records,
        subdir="uci",
        overwrite=overwrite,
        label=catalog_name,
    )
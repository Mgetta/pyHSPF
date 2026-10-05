"""Small, table-first topology builder for one parsed HSPF UCI file.

Topology normalizes; validation judges; lake catalogs persist. Only
``build_topology`` reaches into a UCI object. Everything downstream consumes
explicit source tables and returns four normalized frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import networkx as nx
import pandas as pd

from hspf.core.types import EdgeRole, OperationKey, RoutingSource
from hspf.model import topology
from hspf.model import topology


OPERATIONS_COLUMNS = tuple(
    "operation opnid name lkfg nexits gener_opcode opn_order "
    "in_opn_sequence has_gen_info".split()
)
CONNECTIONS_COLUMNS = tuple(
    "routing_source source_operation source_id target_operation target_id "
    "afactr mfactor mlno tmemsb1 tmemsb2 source_row".split()
)
MEMBER_TRANSFERS_COLUMNS = tuple(
    "routing_source source_operation source_id source_group source_member "
    "source_sub1 source_sub2 target_operation target_id target_group "
    "target_member target_sub1 target_sub2 mlno tran afactr mfactor "
    "effective_factor source_row".split()
)
EXTERNAL_INPUTS_COLUMNS = tuple(
    "svol dsn filename source_member ssystem target_operation target_id "
    "target_member target_group mfactor tran source_row".split()
)

LAND_OPERATIONS = frozenset({"PERLND", "IMPLND"})
GENINFO_NAMES = {"PERLND": "LSID", "IMPLND": "LSID", "RCHRES": "RCHID"}
SCHEMATIC_CONNECTION = dict(
    SVOL="source_operation", SVOLNO="source_id", TVOL="target_operation",
    TVOLNO="target_id", AFACTR="afactr", MLNO="mlno",
    TMEMSB1="tmemsb1", TMEMSB2="tmemsb2",
)
NETWORK_CONNECTION = dict(
    SVOL="source_operation", SVOLNO="source_id", TVOL="target_operation",
    target_id="target_id", MFACTOR="mfactor", source_row="source_row",
)
EXTERNAL_INPUT = dict(
    SVOL="svol", SVOLNO="dsn", SMEMN="source_member", SSYST="ssystem",
    TVOL="target_operation", target_id="target_id", TMEMN="target_member",
    TGRPN="target_group", MFACTOR="mfactor", TRAN="tran", source_row="source_row",
)
NETWORK_MEMBER = dict(
    SVOL="source_operation", SVOLNO="source_id", SGRPN="source_group",
    SMEMN="source_member", SMEMSB1="source_sub1", SMEMSB2="source_sub2",
    TVOL="target_operation", target_id="target_id", TGRPN="target_group",
    TMEMN="target_member", TMEMSB1="target_sub1", TMEMSB2="target_sub2",
    TRAN="tran", MFACTOR="mfactor", source_row="source_row",
)


@dataclass(frozen=True)
class TopologySourceTables:
    """Direct UCI tables needed to build model topology."""

    opn_sequence: pd.DataFrame
    schematic: pd.DataFrame
    network: pd.DataFrame
    ext_sources: pd.DataFrame
    files: pd.DataFrame
    geninfo: Mapping[str, pd.DataFrame]
    gener_opcode: pd.DataFrame
    mass_link_tables: Mapping[str, pd.DataFrame]
    ftable_names: tuple[str, ...]


@dataclass(frozen=True)
class ModelTopology:
    """Normalized topology frames for one UCI model."""

    operations: pd.DataFrame
    connections: pd.DataFrame
    member_transfers: pd.DataFrame
    external_inputs: pd.DataFrame
    ftable_ids: frozenset[int]

    def operation_keys(self, *, running_only: bool = True) -> set[OperationKey]:
        frame = self.operations
        if running_only:
            frame = frame.loc[frame["in_opn_sequence"]]
            
        # Drop NAs first to minimize the iteration loop
        subset = frame[["OPERATION", "OPNID"]].dropna()
        
        return {
            OperationKey(str(op), int(opnid))
            # index=False drops the index, name=None returns a standard tuple
            for op, opnid in subset.itertuples(index=False, name=None)
        }

    def runnable_connections(self) -> pd.DataFrame:
        keys = {(key.operation, key.opnid) for key in self.operation_keys()}
        
        # Early exit if empty DataFrame or empty keys
        if self.connections.empty or not keys:
            return self.connections.copy()
            
        df = self.connections
        
        # Create MultiIndexes for source and target pairs
        source_idx = pd.MultiIndex.from_arrays([df['SVOL'], df['SVOLNO']])
        target_idx = pd.MultiIndex.from_arrays([df['TVOL'], df['TVOLNO']])
        
        # Apply vectorized boolean mask
        mask = source_idx.isin(keys) & target_idx.isin(keys)
        
        return df.loc[mask].copy()

    def reach_edges(self) -> pd.DataFrame:
        frame = self.runnable_connections()
        return frame.loc[(frame["SVOL"] == "RCHRES") & (frame["TVOL"] == "RCHRES")].copy()

    def land_to_reach(self) -> pd.DataFrame:
        frame = self.runnable_connections()
        mask = [infer_edge_role(row.SVOL, row.TVOL) == EdgeRole.LAND_TO_REACH for row in frame.itertuples(index=False)]
        return frame.loc[mask].copy()

    def precip_assignments(self) -> pd.DataFrame:
        frame = self.external_inputs
        return frame.copy() if frame.empty else frame.loc[frame["target_member"] == "PREC"].copy()


def build_topology(uci: Any) -> ModelTopology:

    schematic = uci.table('SCHEMATIC')
    schematic['MLNO'] = schematic['MLNO'].str.strip()
    schematic['routing_source'] = 'schematic'

    network = uci.table('NETWORK') if 'NETWORK' in uci.block_names() else pd.DataFrame()
    network.rename(columns = {'TOPFST':'TVOLNO'}, inplace=True)
    network['effective_factor'] = network['MFACTOR'].copy()
    network['routing_source'] = 'network'
    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'] = ext_sources['SVOL'].str.upper().replace({'WDM': 'WDM1'})

    files = uci.table('FILES')
    files['FTYPE'] = files['FTYPE'].str.upper().replace({'WDM': 'WDM1'})

    opn_sequence = uci.table('OPN SEQUENCE')
    geninfo = pd.concat([uci.table(operation, "GEN-INFO").assign(OPERATION=operation) for operation in ['PERLND','IMPLND','RCHRES']])
    geninfo = geninfo[['LSID','NEXITS','LKFG','RCHID','OPERATION']].reset_index()
    geninfo['has_geninfo'] = True
    gener_opcode = uci.table('GENER', 'OPCODE').reset_index() if 'GENER' in uci.block_names() else pd.DataFrame()
    gener_opcode['has_gener_opcode'] = True
    gener_opcode['OPERATION'] = 'GENER'
    ftable_names = tuple(uci.table_names('FTABLES'))

    operations = opn_sequence[['OPERATION','SEGMENT']].rename(columns = {'SEGMENT': 'OPNID'})
    operations['in_opn_sequence'] = True
    operations = pd.merge(operations, geninfo, on = ['OPERATION','OPNID'],how='outer')
    operations = pd.merge(operations, gener_opcode, on = ['OPERATION','OPNID'], how='outer')
    operations['in_opn_sequence'] = operations['in_opn_sequence'].fillna(False).astype(bool)
    operations['has_geninfo'] = operations['has_geninfo'].fillna(False).astype(bool)
    operations['has_gener_opcode'] = operations['has_gener_opcode'].fillna(False).astype(bool)

    mass_links = []
    for table_name in uci.table_names('MASS-LINK'):
        table = uci.table('MASS-LINK', table_name)
        mlno = table_name.split('MASS-LINK')[-1].strip()
        table['MLNO'] = mlno
        table['table_name'] = table_name
        mass_links.append(table)
    mass_links = pd.concat(mass_links, ignore_index=True)
    mass_links['MLNO'] = mass_links['MLNO'].astype("string")
    mass_links['table_name'] = mass_links['table_name'].astype("string")

    schematic_masslinks = pd.merge(schematic, mass_links, on=['MLNO', 'SVOL', 'TVOL'], how='left',suffixes=['_schematic','_masslink'])
    schematic_masslinks['TMEMSB1'] = _prefer(schematic_masslinks['TMEMSB1_schematic'], schematic_masslinks['TMEMSB1_masslink'])
    schematic_masslinks['TMEMSB2'] = _prefer(schematic_masslinks['TMEMSB2_schematic'], schematic_masslinks['TMEMSB2_masslink'])
    schematic_masslinks['effective_factor'] = schematic_masslinks['AFACTR']*schematic_masslinks['MFACTOR']

    member_transfers = pd.concat([network, schematic_masslinks], ignore_index=True)

    grouped = network.groupby(['TVOL', 'TVOLNO', 'SVOL', 'SVOLNO'])
    network_connections = grouped.first()
    is_identical = grouped['MFACTOR'].nunique(dropna=False) == 1
    network_connections['MFACTOR'] = network_connections['MFACTOR'].where(is_identical, pd.NA)
    network_connections = network_connections.reset_index()
    network_connections['effective_factor'] = network_connections['MFACTOR'].copy()
    connections = pd.concat([schematic,network_connections])
    connections = connections.reset_index(drop=True)

    external_inputs = pd.merge(ext_sources, files, left_on = 'SVOL', right_on = 'FTYPE', how = 'left')

    ftable_ids = tuple([int(ftable_name.split('FTABLE')[-1].strip()) for ftable_name in ftable_names])

    return ModelTopology(
        operations = operations,
        connections = connections,
        member_transfers = member_transfers,
        external_inputs = external_inputs,
        ftable_ids = ftable_ids,
    )



def infer_edge_role(source_operation: Any, target_operation: Any) -> EdgeRole:
    if source_operation in LAND_OPERATIONS and target_operation == "RCHRES":
        return EdgeRole.LAND_TO_REACH
    if source_operation in LAND_OPERATIONS and target_operation in LAND_OPERATIONS:
        return EdgeRole.LAND_TO_LAND
    if source_operation == "RCHRES" and target_operation == "RCHRES":
        return EdgeRole.REACH_TO_REACH
    return EdgeRole.UTILITY


def afactr_semantics(source_operation: Any) -> str:
    return "area" if source_operation in LAND_OPERATIONS else "count" if source_operation == "GENER" else "factor"


def network_area_basis(row: pd.Series) -> bool:
    return row.get("routing_source") == RoutingSource.NETWORK.value and infer_edge_role(row.get("source_operation"), row.get("target_operation")) == EdgeRole.LAND_TO_REACH


def _prefer(first: pd.Series, second: pd.Series) -> pd.Series:
    return first.where(first.notna() & (first.astype(str).str.strip() != ""), second)


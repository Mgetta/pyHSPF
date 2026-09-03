# -*- coding: utf-8 -*-
"""
Schema definitions for parsing HSPF UCI fixed-width tables.

Loads ParseTable.csv once at import time and converts it into frozen
ColumnSpec and TableSchema objects.  These replace the raw parseTable
DataFrame, the delimiters() function, and all the per-block parser
class overrides from the old parsers.py module.

Usage
-----
    from hspf.schema import SCHEMAS, resolve_schema, get_block_names

    schema = resolve_schema('PERLND', 'PWAT-PARM2')
    # schema.columns  → tuple of ColumnSpec
    # schema.column_width('LZSN')  → 10
    # schema.line_width  → 80

    # Numbered tables get their number stripped automatically:
    schema = resolve_schema('FTABLES', 'FTABLE42')
    # → looks up SCHEMAS[('FTABLES', 'FTABLE')]
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data path — same CSV your current code uses, no changes to the file
# ---------------------------------------------------------------------------

_CSV_PATH = Path(__file__).parent.parent / 'data' / 'ParseTable.csv'


# ---------------------------------------------------------------------------
# ColumnSpec — one column in a fixed-width table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnSpec:
    """Definition of a single fixed-width column.

    Attributes
    ----------
    name : str
        Column name as it appears in ParseTable.csv (e.g. 'LZSN', 'OPNID').
    dtype : str
        One of 'C' (character/string), 'I' (integer), 'R' (real/float).
    start : int
        Zero-based start position in the 80-char line (inclusive).
    stop : int
        Zero-based stop position in the 80-char line (exclusive).
    """

    name: str
    dtype: str   # 'C', 'I', or 'R'
    start: int
    stop: int

    @property
    def width(self) -> int:
        return self.stop - self.start

    @property
    def pd_dtype(self) -> str:
        return _PD_DTYPE_MAP[self.dtype]


_PD_DTYPE_MAP = {'I': 'Int64', 'C': 'string', 'R': 'float64'}


# ---------------------------------------------------------------------------
# TableSchema — complete column layout for one (block, table) pair
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TableSchema:
    """Frozen column layout for a UCI sub-table.

    Attributes
    ----------
    block : str
        Block name from the CSV (e.g. 'PERLND', 'FTABLES').
    table : str
        Canonical table name from the CSV (e.g. 'PWAT-PARM2', 'FTABLE').
        This is the name *without* any trailing instance number.
    columns : tuple of ColumnSpec
        Ordered column definitions INCLUDING the synthetic 'comments'
        column appended at the end.
    index_col : str or None
        When set (e.g. 'OPNID'), parse_table() will call
        df.set_index(index_col) after building the DataFrame.
    """

    block: str
    table: str
    columns: tuple  # tuple[ColumnSpec, ...]
    index_col: Optional[str] = None

    @property
    def line_width(self) -> int:
        return max(c.stop for c in self.columns)

    @property
    def column_names(self) -> list:
        return [c.name for c in self.columns]

    @property
    def pd_dtypes(self) -> dict:
        return {c.name: c.pd_dtype for c in self.columns}

    def column(self, name: str) -> ColumnSpec:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(
            f"Column '{name}' not found in schema ({self.block}, {self.table}). "
            f"Available: {self.column_names}"
        )

    def column_width(self, name: str) -> int:
        return self.column(name).width


# ---------------------------------------------------------------------------
# Configuration — which blocks index by OPNID
# ---------------------------------------------------------------------------

OPNID_INDEXED_BLOCKS = frozenset({
    'PERLND', 'IMPLND', 'RCHRES', 'COPY', 'GENER',
})

# Blocks whose table names in the UCI file carry a user-defined trailing
# number (e.g. "FTABLE42", "MASS-LINK3", "MONTH-DATA5").  The CSV stores
# a single canonical name without any number.  When resolving a schema we
# need to strip the trailing digits to recover that canonical name.
#
# NOT every block does this — PERLND tables like "PWAT-PARM2" have the "2"
# baked into the CSV as part of the canonical name.  Only the blocks listed
# here use user-assigned instance numbers.
NUMBERED_TABLE_BLOCKS = frozenset({
    'FTABLES',
    'MASS-LINK',
    'MONTH-DATA',
})

CUSTOM_BLOCKS = frozenset({'GLOBAL', 'OPN SEQUENCE'})

UNIMPLEMENTED_BLOCKS = frozenset({
    'DISPLY', 'DURANL', 'MUTSIN', 'BMPRAC', 'REPORT',
    'PATHNAMES', 'FORMATS', 'SHADE', 'SPEC-ACTIONS', 'CATEGORY',
})


# ---------------------------------------------------------------------------
# load_schemas() — build the SCHEMAS dict from ParseTable.csv
# ---------------------------------------------------------------------------

def load_schemas(csv_path: Path) -> dict:
    """Read ParseTable.csv and return {(block, table): TableSchema}."""
    df = pd.read_csv(
        csv_path,
        dtype={'width': 'Int64', 'start': 'Int64',
               'stop': 'Int64', 'space': 'Int64'},
    )

    schemas = {}

    for (block, table), grp in df.groupby(['block', 'table']):
        cols = tuple(
            ColumnSpec(
                name=str(row['column']),
                dtype=str(row['dtype']),
                start=int(row['start']),
                stop=int(row['stop']),
            )
            for _, row in grp.iterrows()
        )

        # Append synthetic 'comments' column
        last_stop = cols[-1].stop
        cols = cols + (
            ColumnSpec(name='comments', dtype='C',
                       start=last_stop, stop=last_stop),
        )

        index_col = 'OPNID' if block in OPNID_INDEXED_BLOCKS else None

        schemas[(block, table)] = TableSchema(
            block=block,
            table=table,
            columns=cols,
            index_col=index_col,
        )

    return schemas


SCHEMAS: dict = load_schemas(_CSV_PATH)



def _strip_instance_number(table_name: str) -> str:
    """Strip trailing digits from a table name to recover the canonical name.

    This is the same logic as split_number() in uci.py but returns only the
    text portion.

    In the UCI file, numbered blocks produce table names like:
        'FTABLE42'  → canonical 'FTABLE'
        'MASS-LINK3' → canonical 'MASS-LINK'
        'MONTH-DATA5' → canonical 'MONTH-DATA'

    For non-numbered blocks the name is returned unchanged:
        'PWAT-PARM2' → 'PWAT-PARM2'  (the '2' is part of the canonical name)
        'GEN-INFO'   → 'GEN-INFO'

    Examples
    --------
    >>> _strip_instance_number('FTABLE42')
    'FTABLE'
    >>> _strip_instance_number('MASS-LINK3')
    'MASS-LINK'
    >>> _strip_instance_number('PWAT-PARM2')
    'PWAT-PARM2'
    """
    head = table_name.rstrip('0123456789')
    return head.strip()


# ---------------------------------------------------------------------------
# resolve_schema() — the ONE function that replaces parserSelector + overrides
# ---------------------------------------------------------------------------

def resolve_schema(block: str, table_name: str) -> TableSchema:
    """Look up the correct TableSchema for a (block, table_name) pair.

    For most blocks, looks up (block, table_name) directly in SCHEMAS.

    For blocks in NUMBERED_TABLE_BLOCKS (FTABLES, MASS-LINK, MONTH-DATA),
    the table_name found in the UCI file includes a user-assigned instance
    number (e.g. 'FTABLE42', 'MASS-LINK3').  The CSV only stores the
    canonical name without the number ('FTABLE', 'MASS-LINK', 'MONTH-DATA').
    This function strips trailing digits to recover that canonical name
    before looking up the schema.

    This replaces:
      - parserSelector[block]  (class dispatch)
      - ftableParser hardcoding   delimiters('FTABLES', 'FTABLE')
      - masslinkParser hardcoding delimiters('MASS-LINK', 'MASS-LINK')
      - monthdataParser hardcoding delimiters('MONTH-DATA', 'MONTH-DATA')
      - standardParser/operationsParser calling delimiters(block, table_name)

    Parameters
    ----------
    block : str
        Block name from the UCI file (e.g. 'PERLND', 'FTABLES').
    table_name : str
        Table name as it appears in the UCI file.  May include a trailing
        instance number for numbered blocks (e.g. 'FTABLE42').

    Returns
    -------
    TableSchema

    Raises
    ------
    KeyError
        If no schema exists for the resolved key.
    """
    if block in NUMBERED_TABLE_BLOCKS:
        canonical = _strip_instance_number(table_name)
        key = (block, canonical)
    else:
        key = (block, table_name)

    try:
        return SCHEMAS[key]
    except KeyError:
        raise KeyError(
            f"No schema found for block='{block}', table='{table_name}' "
            f"(resolved key={key}). "
            f"Check that ParseTable.csv has rows for this combination."
        ) from None


# ---------------------------------------------------------------------------
# Helpers for uci.py — block/table name validation
# ---------------------------------------------------------------------------

def get_block_names() -> frozenset:
    """Return every unique block name that has a schema defined."""
    return frozenset(block for block, _ in SCHEMAS.keys())


def get_table_names() -> frozenset:
    """Return every unique canonical table name that has a schema defined."""
    return frozenset(table for _, table in SCHEMAS.keys())


def has_simple_table(block: str) -> bool:
    """Check whether a block uses a single 'na' table (simple block)."""
    return (block, 'na') in SCHEMAS
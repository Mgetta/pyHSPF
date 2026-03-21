# UCI Module

## Overview

The `hspf.uci` module provides a Python interface for reading, manipulating,
and writing HSPF (Hydrological Simulation Program – Fortran) **UCI** (User
Control Input) files.

A UCI file is the primary configuration for an HSPF simulation.  It uses a
fixed-width, block-oriented text format that describes the model's operations,
parameters, external data sources, network connectivity, and global settings.

---

## Architecture

The module is organized into two layers:

| Layer | Description |
|---|---|
| **`UCI` class** | The main user-facing API. Lazily parses individual tables on demand and provides methods to query, update, and write the model configuration. |
| **Helper functions** | Module-level functions that operate on a `UCI` instance to perform common initialization and formatting tasks. |

Internally, the raw UCI text is converted into a nested dictionary of `Table`
objects (from `hspf.parser.parsers`) keyed by `(block, table_name, table_id)`
tuples.  Each `Table` wraps the fixed-width lines and can parse them into a
`pandas.DataFrame` using column definitions stored in
`data/ParseTable.csv`.

### Key Concepts

| Term | Description |
|---|---|
| **Block** | Top-level section of a UCI file (e.g. `GLOBAL`, `PERLND`, `RCHRES`, `FILES`, `EXT SOURCES`). |
| **Table** | A named parameter set inside a block (e.g. `PWAT-PARM2`, `GEN-INFO`, `BINARY-INFO`). |
| **Operation** | A hydrologic modeling element: pervious land (`PERLND`), impervious land (`IMPLND`), stream reach / reservoir (`RCHRES`), general operation (`GENER`), or copy operation (`COPY`). |
| **OPNID** | Operation ID — a numeric identifier unique within an operation type. |
| **Table ID** | A zero-based ordinal that distinguishes duplicate table names within a block (e.g. multiple `QUAL-PROPS` tables). |

---

## Quick Start

```python
from hspf.uci import UCI

# Load a UCI file
model = UCI("path/to/model.uci")

# Retrieve a parsed table as a DataFrame
pwat = model.table("PERLND", "PWAT-PARM2")

# List all blocks in the file
print(model.block_names())

# List tables within a block
print(model.table_names("PERLND"))

# Modify a parameter — multiply all LZSN values by 1.5
model.update_table(1.5, "PERLND", "PWAT-PARM2", 0, columns="LZSN", operator="*")

# Write the updated UCI
model.write("path/to/model_updated.uci")
```

---

## UCI Class

### Constructor

```python
UCI(filepath, infer_metzones=True)
```

| Parameter | Type | Description |
|---|---|---|
| `filepath` | `str` or `Path` | Path to the `.uci` file. |
| `infer_metzones` | `bool` | When `True` (default), meteorological zones and landcover assignments are inferred from `EXT SOURCES`. |

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `filepath` | `Path` | Absolute path to the source UCI file. |
| `name` | `str` | Model name derived from the file stem. |
| `lines` | `list[str]` | Raw non-blank lines read from the UCI file. |
| `uci` | `dict` | Mapping of `(block, table_name, table_id)` → `Table`. |
| `valid_opnids` | `dict[str, list[int]]` | Active operation IDs by operation type. |
| `network` | `reachNetwork` | Directed graph of the model's reach network. |
| `opnid_dict` | `dict[str, DataFrame]` | Meteorological-zone / landcover mapping per operation (only when `infer_metzones=True`). |
| `wdm_paths` | `list[Path]` | Resolved paths to WDM files. |
| `hbn_paths` | `list[Path]` | Resolved paths to HBN output files. |

### Table Access Methods

#### `table(block, table_name='na', table_id=0, drop_comments=True)`

Parse and return a UCI table as a `pandas.DataFrame`.

Tables are parsed lazily — the first call triggers the fixed-width parser.
For operation blocks the returned DataFrame is indexed by `OPNID` after
expanding any operation-ID ranges and filtering to `valid_opnids`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `block` | `str` | — | Block name (e.g. `'PERLND'`, `'FILES'`). |
| `table_name` | `str` | `'na'` | Sub-table name. Use `'na'` for single-table blocks. |
| `table_id` | `int` | `0` | Ordinal index for duplicate table names. |
| `drop_comments` | `bool` | `True` | Remove comment rows and the `comments` column. |

**Returns:** `pandas.DataFrame` — A copy of the parsed table.

#### `table_names(block)`

Return the unique sub-table names present in a block.

#### `block_names()`

Return the set of top-level block names present in the UCI file.

#### `table_lines(block, table_name='na', table_id=0)`

Return a copy of the raw fixed-width text lines for a table.

#### `replace_table(table, block, table_name='na', table_id=0)`

Replace the data of an entire table.

### Table Modification Methods

#### `update_table(value, operation, table_name, table_id, ...)`

Update values within a single table using an arithmetic operator.

```python
update_table(value, operation, table_name, table_id,
             opnids=None, columns=None, operator='*', axis=0)
```

Supported operators:

| Operator | Effect |
|---|---|
| `'*'` | Multiply existing values by `value`. |
| `'/'` | Divide existing values by `value`. |
| `'+'` | Add `value` to existing values. |
| `'-'` | Subtract `value` from existing values. |
| `'set'` | Overwrite existing values with `value`. |
| `'chuck'` | Apply the monthly-concentration "chuck" adjustment. Only valid for `MON-IFLW-CONC` and `MON-GRND-CONC` tables. |

### Simulation Configuration Methods

#### `set_simulation_period(start_year, end_year)`

Set the simulation window to January 1 of `start_year` through December 31
of `end_year`.

#### `set_echo_flags(flag1, flag2)`

Set the RUN INTERP and OUTPT level flags in the GLOBAL block.

#### `initialize(name=None, default_output=4, n=5, reach_ids=None)`

Run the full initialization sequence: configure FILES, BINARY-INFO,
GEN-INFO, and QUAL-ID tables.

#### `initialize_binary_info(default_output=4, reach_ids=None)`

Re-initialize only the BINARY-INFO and GEN-INFO tables.

### Write Methods

#### `write(new_uci_path)`

Serialize internal state and write to a new UCI file.

#### `write_tpl(tpl_char='~', new_tpl_path=None)`

Write as a PEST template (`.tpl`) file with the `ptf` header.

#### `add_parameter_template(block, table_name, table_id, column, ...)`

Insert PEST/PEST++ parameter template markers into a table column.

```python
add_parameter_template(block, table_name, table_id, column,
                       parname=None, tpl_char='~', opnids=None,
                       single_template=True, group_id='')
```

**Returns:** `list[str]` — Unique PEST parameter names inserted.

### Query Methods

#### `get_filepaths(file_extension)`

Return resolved paths to FILES entries matching the given extension.

#### `get_dsns(operation, opnid, smemn)`

Look up external-source data-set numbers for an operation member.  Joins
`EXT SOURCES` and `FILES` tables.

#### `get_metzones()`

Infer meteorological-zone assignments from `EXT SOURCES`.

**Returns:** `dict[str, DataFrame]` — Keys are `'PERLND'`, `'IMPLND'`,
`'RCHRES'`.

#### `build_targets()`

Build a landcover-target summary DataFrame for calibration.

---

## Module-Level Helper Functions

### File and Model Setup

#### `setup_files(uci, name, n=5)`

Configure the FILES table for a new model — strips directory prefixes, removes
PLT entries, and creates `n` BINO (binary output) file slots.

#### `setup_geninfo(uci)`

Distribute binary output files across operations in GEN-INFO by splitting
operations evenly across available BINO unit numbers.

#### `setup_binaryinfo(uci, default_output=4, reach_ids=None)`

Set default output print levels in BINARY-INFO tables for all operation types.

#### `setup_qualid(uci)`

Standardize QUAL-ID names (`'NH3+NH4'`, `'NO3'`, `'ORTHO P'`, `'BOD'`) in
QUAL-PROPS tables for both PERLND and IMPLND.

### Model Execution

#### `run_model(uci_file, wait_for_completion=True)`

Launch the WinHSPFLt executable to run an HSPF simulation.

### Parsing Utilities

#### `reader(filepath)`

Read a UCI file and return non-blank lines, truncated to 80 characters
(the standard UCI column width).

#### `build_uci(lines)`

Convert raw UCI text lines into a dictionary of `Table` objects keyed by
`(block, table_name, table_id)` tuples.

#### `get_blocks(lines)`

Identify top-level block boundaries by scanning for matching
`<BLOCK>` / `END <BLOCK>` delimiter pairs.

#### `format_opnids(table, valid_opnids)`

Expand operation-ID ranges (e.g. `"1 10"` → `[1, 2, ..., 10]`) and set the
OPNID index.

#### `expand_extsources(data, valid_opnids)`

Expand target-operation ID ranges in the EXT SOURCES table.

### Adjustment Utilities

#### `chuck(adjustment, table)`

Apply the "chuck" monthly-concentration adjustment algorithm.  For each pair
of adjacent months, the minimum (when increasing) or maximum (when decreasing)
value is adjusted by the given factor.

### Other Utilities

#### `decompose_perlands(metzones, landcovers)`

Map composite perland IDs to their `(metzone, landcover)` components.

#### `split_number(s)`

Split a string into a text head and trailing numeric tail.

#### `insert_rows(insertion_point, a, b, drop=True, reset_index=True)`

Insert rows from one DataFrame into another at a specified position.

#### `keep_valid_opnids(table, opnid_column, valid_opnids)`

Filter a table to retain only rows with valid operation IDs.

#### `RUN_comments(lines)`

Extract comment lines that appear before the `RUN` keyword.

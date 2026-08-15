# HSPF Lake — Phased Implementation Plan

**Status:** Draft for review — companion to [architecture.md](architecture.md) §11
**Scope:** Concrete, file-level implementation guidance for Phases 0–6. Each phase
lists its objective, ordered work items, an explicit file-impact table for the
existing codebase, and exit criteria.

Conventions used in the impact tables:

- **Create** — new file/package.
- **Move** — relocate with minimal or no behavior change.
- **Split** — one existing file becomes two or more targets.
- **Modify** — behavior or imports change in place.
- **Shim** — the old path remains as a thin re-export module emitting
  `DeprecationWarning`, so existing imports keep working until Phase 5.
- **Supersede** — kept working but no longer the recommended path; deleted or
  frozen in Phase 5.

---

## Baseline inventory (what exists today)

The plan below refers to these facts repeatedly; recorded here once.

**Packaging.** `pyproject.toml`: package `hspf` v2.2.1, hatchling, `src/` layout.
`src/hspf/__init__.py` is **empty** — every consumer imports module paths directly
(`from hspf.uci import UCI`, `from hspf import reports`), which makes the shim
strategy cheap. Declared dependencies are missing several actual imports:
`duckdb` (used by `warehouse.py`, `build_warehouse.py`), `xarray` (used by
`xarray_utils.py`), `pyarrow` (needed for Parquet), `pytest` (tests); `pathlib` is
declared but is stdlib. `build_warehouse.load_to_warehouse()` (line ~266) inlines
`from pyhcal.repository import Repository` — an external package acting as the
model locator (model name → UCI path).

**Modules.**

| File | Contents relevant to the plan |
|---|---|
| `src/hspf/uci.py` | `UCI` class: parse/edit/write UCI, `table()`, `update_table()`, `set_simulation_period()`, `get_metzones()`, `get_dsns()`, `get_filepaths()`; engine-run bits `UCI._run()` (~line 604) and module `run_model()` (~871); output-config writers `initialize()`/`initialize_binary_info()` (~747/795, via `setup_binaryinfo`/`setup_geninfo`); `build_targets()` (~821); builds `self.network = reachNetwork(self)` (~105) |
| `src/hspf/parser/parsers.py` | Fixed-width `Parser` subclasses per block type; `parseTable` (loaded from `data/ParseTable.csv`) drives column specs + R/I/C dtypes |
| `src/hspf/parser/graph.py` | `create_graph(uci)` (~54); traversal helpers (`upstream_network`, `subset_network`, `ancestors`, …); `catchment` class (~462); `reachNetwork` class (~519) with `subwatersheds()`, `drainage_area()`, `get_opnids()`, `calibration_order()` — the workhorse behind most reports |
| `src/hspf/hbn.py` | `hbnClass` (~667): binary map (`map_hbn` ~766), `read_data()` (~817), `infer_opnids/activity`, per-file `get_time_series`/`get_multiple_timeseries`; `hbnInterface` (~352): multi-file facade, `get_multiple_timeseries(..., long_format=...)` (~422), `get_perlnd/implnd/reach_constituent` (~466/485/505), `output_names()` (~534), `_mapn` (~567); module-level transform helpers `get_simulated_*` (~113–350) |
| `src/hspf/wdm.py` / `src/hspf/wdmReader.py` | `wdmInterface`, `hdf5WDM`, `WDM`; `readWDM()` (WDM→HDF5, numba), `get_wdm_data_set()`; the two files contain duplicated date/bit-twiddling helpers (`_splitdate`, `_bits_to_date`, `_increment_date`, …) |
| `src/hspf/hspfModel.py` | `hspfModel` facade composing `UCI` + `hbnInterface` + `wdmInterface` + `ReportsAccessor` + `outputWriter`; `validate_uci()` (~91) **auto-runs the engine** if HBNs are missing; `run_model()` (~111); `run_uci()` (~197), `run_batch_files()` (~206, concurrent.futures); hard-coded `bin\WinHSPFLt\WinHspfLt.exe` path |
| `src/hspf/helpers.py` | `get_tcons()` (~35): constituent alias → HBN series names per operation — a de-facto lexicon seed; `nutrient_name/nutrient_id`; small date/landcover helpers |
| `src/hspf/outputs.py` | `outputWriter` CSV export class; calls `reports.average_annual_watershed_loading` / `average_annual_catchment_loading` which are **no longer exported** by `reports/__init__.py` (latent `AttributeError`) |
| `src/hspf/reports/__init__.py` | Re-exports ~70 functions; `ReportsAccessor` (~133) — note `total_phosphorous()` (~309) references an undefined name (latent `NameError`); `get_catchments()` (~315); `_operation_metadata()` (~339) references a module where it means an instance (latent bug) |
| `src/hspf/reports/loading.py` | `get_constituent_loading`, `_join_catchments` (joins `uci.network.subwatersheds()`), `get_catchment_loading`, `get_watershed_loading`, `constituent_loading_summary`, `loading_summary`, `catchment/watershed_loading_summary`, `catchment_areas` |
| `src/hspf/reports/nutrients.py` | `MASSLINK_SCHEME` (species → TMEMN/TMEMSB targets); `total_phosphorus`/`total_nitrogen` (~171/131); `_pathway_transform` (~212): filters a MASS-LINK table by TMEMN/TMEMSB, `MFACTOR` fillna(1), sums pathways — **the on-the-fly TP/TN recipe engine**; `_calculate_BOD_*` factors |
| `src/hspf/reports/timeseries.py` | `filter_years/filter_months/aggregate/annual_totals/…` — already a **pure** pandas kernel (no uci/hbn args) |
| `src/hspf/reports/utils.py` | `weighted_mean`, `weighted_output`, `_apply_time_aggregation`, `add_temporal_groups`, period-validation helpers |
| `src/hspf/reports/contributions.py` | `channel_inflows/outflows/fate`, `total_contributions`; `_compute_*` helpers (~266–367) already pure |
| `src/hspf/reports/gener.py` | `transform_timeseries(opcode, A, B, c)` — pure GENER math; `instructions(uci)` — GENER wiring from the UCI |
| `src/hspf/reports/{hydrology,sediment,yields,residence,legacy}.py` | Remaining marts; `legacy.py` holds superseded loading functions + old `Reports` class |
| `src/hspf/xarray_utils.py` | `TimeStep` IntEnum (HBN tcodes 2–5), `TIMESTEP_LABELS`, `PANDAS_FREQ`, `OPERATIONS`, `MAX_OPNID`, `VALID_OPERATION_VARIABLE` (~77, per-operation valid variable sets), `UNITS_BY_VARIABLE` (~120) — **proto-lexicon constants**; `create_timestep_dataset`, `HspfDatasetCollection` |
| `src/hspf/warehouse.py` | DuckDB helpers: `init_hspf_db` (runs `sql/schema.sql`), `connect`, `load_df_to_table`, `add_df_to_table`, `insert_df_into_table`, `drop_model_data` |
| `src/hspf/build_warehouse.py` | `build_model_table` (natural key `model_name/model_year/run_id`), `build_operations/schematic/masslink/extsources/exttargets/network/gener/ftables_table`, `build_parameter_table` (EAV melt via `parseTable` R/I/C), `load_model`/`add_model`/`load_to_warehouse` |
| `src/hspf/sql/schema.sql` | `models` with `UNIQUE(model_name, model_year, run_id)`; `uci.*` tables; `output.timeseries` (long format); `reports.catchment_loading` |
| `src/hspf/data/` | `ParseTable.csv` (parser specs), `Timeseries Catalog/{PERLND,IMPLND,RCHRES}/` (fixed-width variable descriptors: name, dims, units English/Metric, description — lexicon seed), `LandUseNames_Mappings.csv`, `model_landcovers.csv`, `HSPFParameterRanges.csv` |
| `tests/` | `test_graph.py` + `test_uci.py` run against the real `tests/data/Clearwater.uci`; `test_reports.py` imports `hspf.reports._analytics.{timeseries,loading,yields}` which **do not exist** (an earlier partial attempt at this same pure-kernel split — the module fails collection); `test_lagged_contributions.py`, `test_lagrangian_travel_time.py` (mock-based), `test_xarray_utils.py`. No HBN fixture in-repo |
| `docs/` | Sphinx (`index.rst`, `uci.rst`, `uci_class.rst`, `hbn.rst`, `hbn_class.rst`, `reports.rst`, `user-guide/`) |

**Target layering** (architecture §10): `core ← model ← lake ← curated ← api`,
with `workbench` consuming `lake`+`curated`, and `legacy/` shims outside the
dependency chain.

---

## Phase 0 — Characterize (baseline + golden fixtures)

**Objective.** A green test suite, a declared-dependency manifest that matches
reality, and golden output snapshots from the *current* code for 2–3 real models —
the yardstick every later phase is measured against. No architectural change.

### Work items

1. **Repair test collection.** `tests/test_reports.py` lines 11–12 import
   `hspf.reports._analytics.timeseries` and `hspf.reports._analytics.loading`;
   later tests import `_analytics.yields` inline (~lines 706–803). The pure
   functions that exist live at `hspf.reports.timeseries` (`filter_years`,
   `filter_months`, `aggregate`); `compute_load`, `compute_loading_rate`,
   `compute_yield`, `compute_net_load`, `yield_summary` exist nowhere. Repoint the
   imports that have real targets; mark the `_analytics.loading`/`_analytics.yields`
   tests `xfail`/`skip` with reason "pure kernel lands in Phase 4 as
   `hspf.curated`" — they are, in effect, pre-written acceptance tests for Phase 4.
   Also fix the stale docstring reference in `reports/yields.py` (line ~6).
2. **Dependency hygiene.** In `pyproject.toml`: add `duckdb`, `xarray`, `pyarrow`;
   remove `pathlib`; add `[project.optional-dependencies] dev = ["pytest"]`. This
   is required by Phases 2+ and makes the baseline installable from scratch.
3. **Select fixture models.** Choose 2–3 from the 68 covering the semantic surface:
   (a) a simple PERLND/IMPLND/RCHRES model, (b) one with a NETWORK block and GENER
   operations, (c) one producing hourly output. Models (UCI+HBN+WDM) stay outside
   the repo; add `tests/conftest.py` with an `HSPF_FIXTURE_ROOT` env-var fixture
   and `skipif` guards so CI without model data still passes. `tests/data/Clearwater.uci`
   remains the in-repo UCI-only fixture.
4. **Golden snapshot script** (`tests/goldens/make_goldens.py`). For each fixture
   model, drive the **current** API exactly as users do:
   - `hspfModel(uci_file)` → `.reports` (`ReportsAccessor`): `catchment_loading`
     for `['Q','TSS','TP','TN','OP','TKN']`, `watershed_loading(...)`,
     `loading_summary(...)`, `annual_water_budget('PERLND'|'IMPLND'|'RCHRES')`;
   - `reports.nutrients.total_phosphorus` / `total_nitrogen` for PERLND and IMPLND
     at `t_code` 4 and 5 (these become the Phase-3 recipe oracle);
   - raw pulls via `hbnInterface.get_multiple_timeseries` for a sample of
     (operation, activity, tcode) combinations (these become the Phase-2 ingest
     oracle);
   - write each result to `tests/goldens/<model>/<name>.csv` plus a
     `goldens_manifest.json` (package version, git hash, model file fingerprints).
5. **Record known-broken paths — do not fix.** `outputs.py` →
   `reports.average_annual_watershed_loading`/`average_annual_catchment_loading`
   (missing exports); `ReportsAccessor.total_phosphorous` (`NameError`);
   `reports/__init__._operation_metadata` (uses the module `uci` where it needs an
   instance). List them in the goldens manifest as `known_broken`; they scope the
   Phase-5 legacy shims and must not silently start "working differently".

### File impact

| File | Action |
|---|---|
| `tests/test_reports.py` | Modify (repoint/xfail `_analytics` imports) |
| `src/hspf/reports/yields.py` | Modify (docstring only) |
| `pyproject.toml` | Modify (deps) |
| `tests/conftest.py`, `tests/goldens/make_goldens.py`, `tests/goldens/**` | Create |

### Exit criteria

`pytest` collects and passes everywhere (fixture-dependent tests skip cleanly
without model data); goldens generated and committed; `pip install -e .` pulls
every import the package actually makes.

---

## Phase 1 — Core + model layer

**Objective.** Establish the `core/` and `model/` packages by relocation, with
shims at every old path. **Zero behavior change** — goldens must be byte-identical.

### Work items

1. **Create `src/hspf/core/`.**
   - `core/types.py`: move `TimeStep`, `TIMESTEP_LABELS`, `PANDAS_FREQ`,
     `OPERATIONS`, `MAX_OPNID` out of `xarray_utils.py` (lines ~29–65);
     `xarray_utils.py` re-imports them from core (its public names unchanged, so
     `tests/test_xarray_utils.py` still passes). Add the `Block` taxonomy
     (`entity_type × activity`) as a frozen dataclass/enum — used by Phase 2.
   - `core/constituents.py`: move `helpers.get_tcons`, `nutrient_name`,
     `nutrient_id` (the constituent-alias vocabulary).
   - `core/util.py`: move the remaining `helpers.py` functions
     (`decompose_perlands`, `get_months`, `get_adjacent_month`).
   - `core/conventions.py`: new — period-start timestamp rule
     (`shift_to_period_start(index, timestep)`), UNC-path helpers, naming rules.
     Written now, exercised from Phase 2 on.
2. **Create `src/hspf/model/` by relocation.**
   - `uci.py` → `model/uci.py`. Extract engine execution into `model/runner.py`:
     `UCI._run()` (~604), module `run_model()` (~871), plus `run_uci()` and
     `run_batch_files()` from `hspfModel.py` (~197/206) and the `WinHspfLt.exe`
     path constant. `UCI` keeps a thin `_run()` delegating to the runner (shim
     behavior preserved).
   - `parser/parsers.py` → `model/parser/parsers.py` unchanged (verify the
     `data/ParseTable.csv` load path — it resolves relative to the module file).
   - `parser/graph.py` → `model/graph.py` whole (`create_graph`, traversals,
     `catchment`, `reachNetwork`). Update `model/uci.py`'s
     `from .graph import reachNetwork`.
   - `hbn.py` → `model/hbn.py` whole, including the module-level
     `get_simulated_*` helpers (they move again in Phase 5; two moves are cheaper
     than a premature split).
   - `wdm.py` + `wdmReader.py` → `model/wdm.py` (+ `model/_wdm_codec.py` if the
     merge is noisy). Deduplicate the twin date/bit helpers — keep the
     numba-jitted variants, delete the duplicates.
   - `hspfModel.py` → `model/session.py`: class `hspfModel` keeps composition +
     validation (`validate_uci`, `validate_wdms`, `validate_folders`,
     `check_filename_*`, `load_hbn/load_uci/convert_wdms`) and calls
     `model/runner.py` for execution. Leave the surprising auto-run behavior in
     `validate_uci()` (~line 106) untouched but add a docstring warning; removing
     it is a Phase-6 workbench decision.
3. **Shims.** Replace each old module with a re-export:
   `src/hspf/{uci,hbn,wdm,wdmReader,hspfModel,helpers,xarray_utils}.py` and
   `src/hspf/parser/{__init__,parsers,graph}.py` become
   `from hspf.model.uci import *  # noqa` (etc.) plus a module-level
   `DeprecationWarning`. This keeps every existing consumer working unmodified:
   `tests/test_graph.py` (`from hspf.parser import graph`), `tests/test_uci.py`,
   `reports/*` (`from hspf.uci import UCI`, `from hspf.hbn import …`),
   `build_warehouse.py` (`from hspf.parser.parsers import parseTable`),
   `outputs.py`, `warehouse.py`.
4. **Docs.** `docs/uci_class.rst`, `docs/hbn_class.rst`, `docs/uci.rst`,
   `docs/hbn.rst` autodoc targets → `hspf.model.*` (or rely on shims short-term;
   prefer updating so warnings don't leak into built docs).

### File impact

| File | Action |
|---|---|
| `src/hspf/core/{__init__,types,constituents,util,conventions}.py` | Create |
| `src/hspf/model/{__init__,uci,hbn,wdm,graph,runner,session}.py`, `model/parser/` | Create (by move/split) |
| `src/hspf/uci.py`, `hbn.py`, `wdm.py`, `wdmReader.py`, `hspfModel.py`, `helpers.py`, `parser/*` | Shim |
| `src/hspf/xarray_utils.py` | Modify (constants re-imported from `core.types`) |
| `src/hspf/reports/*`, `outputs.py`, `warehouse.py`, `build_warehouse.py` | Unchanged (work via shims) |
| `docs/{uci,uci_class,hbn,hbn_class}.rst` | Modify |

### Exit criteria

Full `pytest` green; goldens regenerate **byte-identical**; `python -W error::DeprecationWarning`
run of the golden script shows warnings only from the expected shims.

---

## Phase 2 — Lake foundation (raw tier + publish)

**Objective.** New runs can be ingested to an immutable raw tier on the share with
manifests, run registration, structural validation, and atomic publish.

### Work items

1. **Create `src/hspf/lake/layout.py`.** Path grammar
   (`raw/run_id=…/block=…/timestep=…[/year=…]`, `catalog/`, `curated/v=…/`,
   `CURRENT.txt` resolution), UNC normalization (uses `core/conventions.py`).
2. **Create `src/hspf/lake/manifest.py`.** Manifest dataclass + read/write/verify:
   file list with row counts, checksums, per-file schema hash; source-file
   fingerprints (UCI/HBN paths, size, mtime, hash); timestamp convention; pipeline
   git hash; validation summary. Manifest write is the *last* step of any publish.
3. **Bulk block reader in the model layer** — the one substantive new piece of
   model-side code. `hbnClass.read_data()` (~817) reads per
   `(operation, opnid, activity, tcode)`; ingest needs per-block frames. Add
   `hbnClass.read_block(operation, activity, tcode) -> wide DataFrame`
   (`opnid × datetime` grain, one column per variable) built directly on the
   binary map from `map_hbn()` (~766), and
   `hbnInterface.iter_blocks() -> Iterator[(Block, tcode, DataFrame)]` using the
   `_mapn` inventory (~567). Reuse — do not duplicate — the dtype/date logic in
   `_get_time_series`.
4. **Create `src/hspf/lake/ingest.py`.**
   - Enumerate blocks via `hbnInterface.iter_blocks()`.
   - **Base-resolution selection:** for each `(block, variable)` keep the smallest
     tcode present (2 < 3 < 4 < 5, per `core.types.TimeStep`); redundant coarser
     series are retained in memory for gate 1 (Phase 3) and *not written*.
   - Normalize timestamps (`core.conventions.shift_to_period_start`); preserve
     native float precision; sort by `(opnid, datetime)`; write Parquet via
     pyarrow (zstd, row-group stats, ~1 M rows/group); hourly blocks split by
     `year=` only if projected file size exceeds ~1 GB.
5. **Create `src/hspf/lake/catalog/runs.py`.** Run registration replacing
   `build_warehouse.build_model_table()`: surrogate `run_id` allocation
   (`r<timestamp>_<model_name>`), core columns per architecture §6.1 (`sim_start`/
   `sim_end` from `uci.table('GLOBAL')` exactly as `build_model_table` extracts
   them today), `attributes` JSON, `status` transitions
   (`active`/`deprecated`/`superseded_by`). Catalog persisted as
   `catalog/runs.parquet` via the same staged publish as data.
6. **Create `src/hspf/lake/validate.py`** with the structural gates: coverage
   (§8.3), schema conformance stub (§8.4 — full check needs the Phase-3 lexicon;
   until then verify names against `xarray_utils.VALID_OPERATION_VARIABLE`),
   sanity (§8.6, entity counts vs `uci.table('OPN SEQUENCE')`).
7. **Create `src/hspf/lake/publish.py`.** Single-writer lock file
   (`_lock/<user>@<host>` with stale-lock detection), `_staging/` on the same
   volume, directory-rename swap, manifest-last, rollback on gate failure.
8. **Move `warehouse.py` → `lake/duck.py`** (shim stays). Same functions,
   reframed: a *local build cache*, not a system of record. `init_hspf_db` now
   loads schema DDL from `lake/schemas/`.
9. **Create `lake/schemas/`** from `sql/schema.sql` (shim/redirect kept until
   Phase 5): split into `catalog.sql`, `raw_contracts.md` (block-table
   conventions; raw schemas are data-driven, not DDL), and add `schema_version`.
   **Corrections relative to `schema.sql`:** `models` natural key
   `(model_name, model_year, run_id)` → surrogate `run_id` + `model_name`
   (`model_year` demoted to an attribute); `output.timeseries` (long) and
   `reports.catchment_loading` marked deprecated — replaced by the raw tier and
   Phase-4 marts respectively.
10. **Backfill entry point `lake/backfill.py`.** Reworks
    `build_warehouse.load_to_warehouse()`'s loop: accept an explicit
    `{model_name: uci_path}` mapping or a locator callable, keeping the `pyhcal`
    `Repository` import optional/injected instead of hard-coded.
11. **Tests.** `tests/test_lake_ingest.py`: ingest the fixture HBN → assert block
    inventory, manifest integrity, and frame-equality between Parquet read-back
    and `hbnInterface.get_multiple_timeseries` goldens (modulo the documented
    timestamp shift). `tests/test_lake_publish.py`: staging atomicity, lock
    contention, manifest-last ordering (temp-dir lake root).

### File impact

| File | Action |
|---|---|
| `src/hspf/lake/{__init__,layout,manifest,ingest,validate,publish,backfill}.py`, `lake/catalog/runs.py`, `lake/schemas/` | Create |
| `src/hspf/model/hbn.py` | Modify (`read_block`, `iter_blocks`) |
| `src/hspf/warehouse.py` | Move → `lake/duck.py` + Shim |
| `src/hspf/sql/schema.sql` | Split → `lake/schemas/` (+ redirect) |
| `src/hspf/build_warehouse.py` | Modify lightly (`build_model_table` superseded by `catalog/runs.py`; rest untouched until Phase 3) |
| `tests/test_lake_*.py` | Create |

### Exit criteria

One fixture model ingested end-to-end onto a temp lake root: raw blocks +
manifest + registered run; re-read equals goldens; publish gates demonstrably
block on injected failures; kill-mid-publish leaves no visible partial run.

---

## Phase 3 — Semantics (catalog compilers + full validation)

**Objective.** The lake becomes self-describing: lexicon, per-run series map,
compiled recipes, unified edges, entities, UCI EAV — enabling gates 1/2/5.

### Work items

1. **`lake/catalog/lexicon.py`.** Parse the fixed-width descriptor files under
   `data/Timeseries Catalog/{PERLND,IMPLND,RCHRES}/` (name, dims, units
   English/Metric, description) into `variables.parquet`. Merge the curated
   constants from `xarray_utils.py` — `VALID_OPERATION_VARIABLE` (~77) and
   `UNITS_BY_VARIABLE` (~120) — and the alias map from
   `core/constituents.get_tcons`. Add the `kind` column
   (flux/state/concentration/…) and default `aggregate_by`/`weight_variable`;
   seed kinds for the variables the marts actually consume first, expand
   opportunistically. Long-term, `xarray_utils`' constants become *generated
   from* the lexicon (Phase 5).
2. **`lake/catalog/series_map.py`.** Per-run provenance compiler:
   - `produced_as` from the UCI `BINARY-INFO` tables
     (`uci.table('PERLND','BINARY-INFO')` etc. — the tables
     `UCI.initialize_binary_info()` writes) and, where outputs route through
     `EXT TARGETS`, from the `AGGST`/`TRAN` columns already captured by
     `build_warehouse.build_exttargets_table()`;
   - observed timestep from the HBN inventory (`hbnInterface._mapn`);
   - `aggregate_by`/`weight_variable` defaulted from the lexicon, with sparse
     per-run/per-entity override rows only where configs differ.
   Cross-check compiled provenance against the HBN's actual tcodes and fail
   loudly on mismatch.
3. **`lake/catalog/recipes.py`.** Compile MASS-LINK into linear recipe rows,
   porting the *selection logic* of `reports/nutrients.py` without executing it:
   `MASSLINK_SCHEME` provides (species → TMEMN/TMEMSB1/TMEMSB2); enumerate
   MASS-LINK tables exactly as `build_warehouse.build_masslink_table()` does
   (`uci.table_names('MASS-LINK')`); apply `_pathway_transform`'s row filter
   (TMEMN/TMEMSB match, `MFACTOR` fillna(1)); resolve **entity → MLNO
   applicability** through SCHEMATIC (`uci.network.subwatersheds()` carries
   `MLNO` per SVOL/SVOLNO); fold in the `_calculate_BOD_*` factors. Emit
   `(derived_variable, run_id, entity_type, entity_id_range, term_order,
   source_block, source_variable, factor, source_ref)`.
   **Oracle test:** a generic recipe evaluator applied to Phase-2 raw must
   reproduce the Phase-0 `total_phosphorus`/`total_nitrogen` goldens within
   float tolerance on all fixture models. This is the go/no-go gate for the
   whole recipe concept.
4. **`lake/catalog/edges.py`.** Union SCHEMATIC + NETWORK into one edge list
   (`link_kind` preserving origin), reusing `build_schematic_table`/
   `build_network_table` extraction and the edge semantics of
   `model/graph.create_graph()`. Add `graph_from_edges(edges_df) -> nx.DiGraph`
   to `model/graph.py` so every existing traversal
   (`upstream_network`, `subset_network`, …) works on catalog edges without a
   `UCI` object — the key enabler for Phase-4 purification. Cross-model links
   come from a small curated seed file (`data/cross_model_links.csv`, new) with
   `target_run_id` resolution at publish time.
5. **`lake/catalog/uci_tables.py`.** Move the remaining builders from
   `build_warehouse.py` — `build_parameter_table` (EAV via `parseTable` R/I/C
   dtypes — keep verbatim; it is good), `build_ftables_table`,
   `build_masslink_table`, `build_extsources_table`, `build_exttargets_table`,
   `build_operations_table`, `build_gener_table` — re-keyed from
   `(model_name, model_year)` to `run_id`. `build_files_table` output goes into
   `runs.attributes` (per architecture: operational metadata, not a table).
   `build_warehouse.py` then becomes a shim over `lake/backfill.py` + catalog
   modules.
6. **`lake/catalog/entities.py`.** OPN SEQUENCE (from `build_operations_table`)
   joined with GEN-INFO `LSID`, met zones (`UCI.get_metzones()`), SCHEMATIC areas
   (as in `UCI.build_targets()` and `reports/__init__.get_catchments()`), and the
   seed CSVs `data/LandUseNames_Mappings.csv` + `data/model_landcovers.csv`.
7. **`lake/catalog/transforms.py`.** Registry of code derivations
   (name, version, code ref, signature). First entries: GENER, wrapping
   `reports/gener.transform_timeseries` (pure) with wiring compiled from
   `reports/gener.instructions(uci)`.
8. **`lake/catalog/gauges.py`.** Schema + loader for the gauge↔reach map
   (curated CSV input; observation *data* ingestion is Phase 6).
9. **Extend `lake/validate.py`.** Gate 1 (cross-resolution: recompute coarse from
   base using `produced_as`, diff vs the engine's own coarse series captured
   during ingest), gate 2 (mass balance across `edges` with SCHEMATIC AFACTR),
   gate 5 (referential integrity: recipes/edges/weights resolve), and complete
   gate 4 against the lexicon.

### File impact

| File | Action |
|---|---|
| `src/hspf/lake/catalog/{lexicon,series_map,recipes,edges,uci_tables,entities,transforms,gauges}.py` | Create |
| `src/hspf/lake/validate.py` | Modify (gates 1/2/5, full 4) |
| `src/hspf/build_warehouse.py` | Split → `lake/catalog/*` + Shim |
| `src/hspf/model/graph.py` | Modify (`graph_from_edges`) |
| `src/hspf/data/cross_model_links.csv` | Create (seed) |
| `src/hspf/reports/nutrients.py`, `reports/gener.py` | Unchanged (serve as oracles/sources) |
| `tests/test_catalog_{lexicon,series_map,recipes,edges}.py` | Create |

### Exit criteria

Fixture models publish with a full catalog; recipe evaluator matches TP/TN
goldens; gate 1 verifies (and then drops) the engine's redundant coarse series;
`build_warehouse.load_to_warehouse` still works via its shim.

---

## Phase 4 — Curated builders (the core refactor)

**Objective.** Port `reports/*` into pure, catalog-driven builders under
`curated/`, producing versioned marts. `reports/*` keeps working untouched until
Phase 5.

**Purification convention** (applies to every port): builder signatures take
frames, never live objects —
`f(raw: BlockReader, cat: Catalog, *, params…) -> DataFrame`. Every
`uci.network.X()` call maps to a catalog equivalent:
`subwatersheds()` → join `entities`+`edges`; `get_opnids()`/`drainage_area()` →
`model.graph` traversals over `graph_from_edges(cat.edges)`;
`uci.opnid_dict` → `entities` columns; direct HBN reads
(`hbn.get_perlnd_constituent`, `get_multiple_timeseries`) → raw-tier scans.

### Work items

1. **Skeleton.** `curated/build.py` (release orchestration: enumerate marts,
   write `curated/v=<release>/mart=…/`, record builder+recipe versions in
   `catalog/releases.parquet`, update `CURRENT.txt` last — uses `lake/publish.py`
   machinery); `curated/derive.py` (the Phase-3 recipe evaluator productionized +
   transform runner); `curated/rollups.py` (generalize
   `reports/timeseries.aggregate`/`annual_totals`/… and
   `reports/utils._apply_time_aggregation`/`add_temporal_groups`/`weighted_mean`
   to honor `aggregate_by` + `weight_variable` from the series map — this is
   where flow-weighted concentration rollups become correct by construction).
2. **Port order and mapping** (each validated against Phase-0 goldens before the
   next starts):
   1. `reports/loading.py` → `curated/marts/loading.py` — highest user value.
      `get_constituent_loading` becomes recipe-aware (`TP`/`TN` route through
      `derive.py`, direct variables through raw scans);
      `_join_catchments`/`catchment_areas` join catalog frames;
      `_filter_to_watershed` uses edge-graph traversal. The hard-coded
      `start_year=1996,end_year=2100` defaults become explicit release
      parameters.
   2. `reports/yields.py` → `curated/marts/yields.py`, and *this* is where the
      missing `_analytics.yields` kernel from the stale tests gets written
      (`compute_yield`, `compute_net_load`, `yield_summary`, …): un-xfail those
      Phase-0 tests and point them at `hspf.curated`.
   3. `reports/hydrology.py` → `curated/marts/hydrology.py` (water budgets need
      WDM met inputs for `avg_annual_precip`/`water_balance`: raw-tier reads plus
      a thin met-inputs adapter — either ingest EXT SOURCES met series in the
      run's raw tier at Phase-2 ingest time [preferred: they're small] or accept
      a WDM path parameter as an interim).
   4. `reports/sediment.py` → `curated/marts/sediment.py`.
   5. `reports/contributions.py` → `curated/marts/contributions.py` — the
      `_compute_*` helpers (~266–367) are already pure and move verbatim.
   6. `reports/residence.py` → `curated/marts/residence.py` — mock-based tests
      (`test_lagged_contributions.py`, `test_lagrangian_travel_time.py`) move
      with it, largely unchanged (they already test pure logic).
   7. `reports/gener.py` execution → `curated/derive.py` transform path
      (registry from Phase 3).
3. **BI shaping.** `curated/bi.py`: long-format constituent extracts; wide UCI
   parameter views by pivoting the EAV catalog (`lake/duck.py` SQL PIVOT of
   `uci.parameters`/`flags`/`properties` per operation type).
4. **Deprecations decided here:** `reports/legacy.py` functions and
   `hbn.get_simulated_*` module helpers are *not* ported — they are subsumed by
   marts + the Phase-5 API; `sql/schema.sql`'s `reports.catchment_loading` table
   is superseded by `mart=loading`.
5. **Tests.** Golden-diff harness `tests/test_marts_golden.py`: for each fixture
   model and mart, curated output == Phase-0 golden (tolerance-aware; document
   any *intentional* diffs, e.g. timestamp convention, in a per-mart
   `DEVIATIONS.md`).

### File impact

| File | Action |
|---|---|
| `src/hspf/curated/{__init__,build,derive,rollups,bi}.py`, `curated/marts/{loading,yields,hydrology,sediment,contributions,residence}.py` | Create (ports) |
| `src/hspf/reports/*` | Unchanged in behavior (source of ports; frozen except bug-fix backports) |
| `tests/test_reports.py` xfailed kernel tests | Modify (un-xfail → `hspf.curated`) |
| `tests/test_marts_golden.py` | Create |
| `tests/test_lagged_contributions.py`, `test_lagrangian_travel_time.py` | Modify (import paths in step 2.6) |

### Exit criteria

All marts reproduce goldens on fixture models; a full curated release builds
end-to-end (`build.py` → versioned folder + `releases.parquet` + `CURRENT.txt`);
a Tableau/Power BI workbook pointed at `mart=loading` + `catalog/runs.parquet`
demonstrates the BI path with zero services.

---

## Phase 5 — API + cutover

**Objective.** A supported public contract; legacy paths shimmed and warned;
the 68-model backfill executed; docs updated.

### Work items

1. **`api/reader.py`.** `Lake` class over `lake/layout.py` + `lake/duck.py`
   (DuckDB `read_parquet(..., union_by_name=true)` scans): `runs()`,
   `entities(run)`, `timeseries(run, block, vars, timestep)`,
   `derived(run, name, …)`, `mart(name, release='current')`, `release()` pinning.
   Manifest verification on open; runs without manifests are invisible.
2. **`api/xr.py`.** Move `create_timestep_dataset`, `HspfDatasetCollection`,
   `_build_valid_mask` from `xarray_utils.py`; units/validity now sourced from
   the lexicon (with the old constants kept as generated fallbacks).
   `tests/test_xarray_utils.py` → `tests/test_api_xr.py`.
3. **`legacy/` package.**
   - `outputs.py` → `legacy/outputs.py`: `outputWriter` re-implemented as thin
     calls into `curated`/`api` (fixing the currently-broken
     `reports.average_annual_*` references as part of the port);
   - `reports/legacy.py` + `hbn.get_simulated_*` → `legacy/reports.py`;
   - `reports/__init__.py` gains `DeprecationWarning`s and delegates ported
     functions to `curated.marts.*` (single implementation, two entry points
     during the deprecation window); fix `ReportsAccessor.total_phosphorous`
     and `_operation_metadata` here (they now delegate, so the fixes are free);
   - root shims from Phase 1 (`hspf/uci.py` etc.) keep warning; `warehouse.py`
     and `build_warehouse.py` shims now emit *removal* notices.
4. **Backfill runbook + execution.** `lake/backfill.py` driven over all 68 models
   (locator = `pyhcal.Repository` adapter), batched with
   `model/runner.run_batch_files` where re-runs are needed; per-model publish;
   spot-check dashboards against known-good numbers; mark superseded prior data.
5. **Docs.** `docs/index.rst`: add architecture + lake user guide toctree
   entries; update `uci.rst`/`hbn.rst`/`reports.rst` module paths; new
   `docs/user-guide/lake.rst` (publish protocol, API examples, BI connection
   recipe); README quickstart.
6. **Packaging.** Version bump to 3.0.0; `[project.optional-dependencies]`
   split (`bi`, `dev`); consider a `hspf-lake` console entry point for
   ingest/publish/backfill commands.

### File impact

| File | Action |
|---|---|
| `src/hspf/api/{__init__,reader,xr}.py`, `src/hspf/legacy/{__init__,outputs,reports}.py` | Create |
| `src/hspf/xarray_utils.py` | Shim (→ `api/xr` + `core.types`) |
| `src/hspf/outputs.py` | Shim (→ `legacy/outputs`) |
| `src/hspf/reports/__init__.py` | Modify (deprecation + delegation) |
| `src/hspf/reports/{loading,yields,hydrology,sediment,contributions,residence,gener,nutrients,timeseries,utils}.py` | Supersede (delegating stubs or frozen) |
| `src/hspf/{warehouse,build_warehouse}.py` shims | Modify (removal notices) |
| `docs/index.rst`, `docs/reports.rst`, `docs/user-guide/**`, `README` | Modify/Create |
| `pyproject.toml` | Modify (3.0.0, extras, entry point) |

### Exit criteria

All 68 models published (raw + catalog + curated release); BI dashboards cut
over to marts; `pytest` green with deprecation warnings only from `legacy/`;
docs build clean.

---

## Phase 6 — Workbench + observations (as needed)

**Objective.** Calibration scratch tier and observation data as lake peers.

### Work items

1. **`workbench/scratch.py`.** A `ScratchLake` on local disk with identical
   layout/schemas (reusing `lake/*` wholesale, different root + relaxed gates:
   gate 1/3 on, mass-balance optional for speed); `promote(run_id)` = full-gate
   publish to the shared lake. Integrates `model/runner.run_batch_files` for
   iteration loops; `model/session.hspfModel` gains a `to_scratch()` convenience.
   Revisit the `validate_uci()` auto-run behavior here — in workbench context it
   becomes an explicit `run_if_stale` flag instead of an assert-side-effect.
2. **Observations.** `lake/observations.py`: ingest gauge series into
   `observations/provider=…/` using the same wide shapes; WDM-sourced series via
   `model/wdm.py` (`readWDM`/`get_wdm_data_set`); populate
   `catalog/gauges.parquet` (Phase-3 schema) with drainage-area ratios and QC
   flags; `api/reader.py` grows `observed(gauge_id, …)` and a
   `paired(run, entity, gauge)` join helper implementing the documented
   model↔gauge semantics.
3. **Calibration metrics (optional).** Post-promotion hook writing NSE/R² etc.
   into `runs.attributes` — closing the loop with `data/HSPFParameterRanges.csv`
   for parameter-bound checks in the workbench.

### File impact

| File | Action |
|---|---|
| `src/hspf/workbench/{__init__,scratch}.py`, `src/hspf/lake/observations.py` | Create |
| `src/hspf/api/reader.py` | Modify (`observed`, `paired`) |
| `src/hspf/model/session.py` | Modify (`to_scratch`, `run_if_stale`) |
| `tests/test_workbench.py`, `tests/test_observations.py` | Create |

### Exit criteria

A calibration loop (edit UCI → run → scratch-ingest → compare vs observations →
promote) works end-to-end on a fixture model without touching the shared lake
until promotion.

---

## Cross-phase dependency summary

```
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5 ──► P6
goldens  moves  raw+   catalog  marts   API+    workbench+
+deps    +shims publish +gates  (ports) cutover observations
```

Hard dependencies: P2 needs P1's `model/` layout and `core/conventions`; P3's
gate 1 needs P2's ingest to retain redundant coarse series; P4 needs P3's
recipes/edges/series-map; P5's backfill needs P4's marts. P6 is independent of
P5's cutover (needs only P2–P4) and can start earlier if calibration pressure
demands.

## Standing cleanup ledger (folded into phases)

| Issue | Where fixed |
|---|---|
| `tests/test_reports.py` imports nonexistent `hspf.reports._analytics` | P0 (xfail) → P4 (kernel lands) |
| Missing deps `duckdb`/`xarray`/`pyarrow`; bogus `pathlib` | P0 |
| Duplicated date/bit helpers in `wdm.py` vs `wdmReader.py` | P1 (merge) |
| Engine-run logic embedded in `UCI._run` / `hspfModel` | P1 (`model/runner.py`) |
| `model_year` inside the warehouse natural key (`sql/schema.sql`) | P2 (`catalog/runs.py`) |
| Hard `pyhcal` import inside `build_warehouse.load_to_warehouse` | P2 (locator injection) |
| `output.timeseries` long table (unscalable) | P2 (raw tier replaces) |
| `outputs.py` calls missing `reports.average_annual_*` | P5 (`legacy/outputs` port) |
| `ReportsAccessor.total_phosphorous` NameError; `_operation_metadata` module/instance bug | P5 (delegation rewrite) |
| Hard-coded `start_year=1996,end_year=2100` defaults across reports | P4 (release parameters) |
| `validate_uci()` silently runs the engine | P6 (`run_if_stale`) |

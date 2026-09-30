# HSPF Model Output Lake — Architecture

**Status:** Draft for review — planning document, no implementation implied yet
**Scope:** Storage, metadata, and consumption architecture for HSPF model outputs across ~68 models; target package layout for `pyhspf`
**Supersedes:** the exploratory conversation in `docs/architecture_chat.txt`

---

## 1. Context

We maintain ~68 HSPF models. Each model has 300–400 operations (PERLNDs, IMPLNDs,
RCHRESs) with ~200 timeseries each at monthly resolution over ~25 years, plus ~400
operations across all models with hourly output. Outputs are produced as HBN binary
files; model configuration lives in UCI files; some inputs/observations live in WDM
files.

**Deployment constraints (fixed):**

- Everything lives on a single agency file share (SMB). No services may be installed
  on it — no PostgreSQL, no query daemon. It is a dumb, shared, read-mostly disk.
- Multiple people consume the data concurrently (Tableau / Power BI / Python).
- All tooling must be open source.
- Pipelines run on individual workstations (DuckDB/pandas locally is fine).

**Scale reality check.** Monthly tier ≈ 1.6 B points ≈ ~13 GB raw / a few GB
compressed. Hourly tier ≈ 17.5 B points upper bound ≈ ~140 GB raw / tens of GB
compressed. This is comfortably single-machine DuckDB territory. **Scale is not the
hard problem; semantics and governance are** — per-entity aggregation rules, derived
variables (TP/TN via MASS-LINK), cross-model routing, and safe publishing to a share
with many readers.

## 2. Goals and non-goals

**Goals**

1. One durable, self-describing home for final model outputs, safely readable by many
   concurrent users from the file share.
2. Semantics captured as data: what each series is, how it was produced, how to
   aggregate it, how to derive compound variables (TP/TN), and how water routes within
   and across models.
3. BI-ready consumption without a live query service.
4. Reproducibility: every published number traceable to a run, source files, and the
   exact version of the transform that produced it.
5. Extensible to: multiple versions/scenarios per model, observation data,
   calibration workflows, and a future move to cloud object storage.

**Non-goals**

- No live database service, no Iceberg/Delta table formats, no distributed compute
  (Trino/Spark). Escape hatches to these must remain open but they are not part of
  this design.
- No attempt to model the full UCI in a normalized relational schema. We extract only
  what the output lake needs (the "translation layer").
- The lake is not a calibration scratchpad. Iterative runs live in a local workbench
  tier (same schemas, different lifecycle) and are *promoted* when blessed.

## 3. Decision summary

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Parquet** files on the share; no Zarr, no DB files on the share | Irregular relational timeseries, write-once/read-many; `.duckdb`/`.sqlite` on SMB with concurrent access risks corruption |
| D2 | **Two-tier lake: `raw/` (immutable) + `curated/` (disposable, rebuilt)** | BI tools reading static Parquet cannot execute join-time semantics (recipes, per-entity rollups). Semantics are *materialized* into curated marts by versioned pipeline code; raw is never edited |
| D3 | Raw grain is **wide-per-block**: one table per `(entity_type × activity × timestep)` | Mirrors HBN structure (near-passthrough ingest); avoids the 200-column sparse "matrix of death"; schema churn is contained per block |
| D4 | Store **base resolution only** in raw; coarser resolutions are curated products | Single source of truth; engine's redundant coarser outputs are used as *validation oracles* at ingest, then dropped |
| D5 | **Surrogate `run_id`** + core columns + JSON-ish flex attributes in the run catalog | Avoids the overloaded natural key (`name_version_scenario_...`); new experiment dimensions never break the schema |
| D6 | Provenance and aggregation are **separate fields**: `produced_as` vs `aggregate_by` (+ optional `weight_variable`) | A single `SUM/LAST/MEAN` enum can't express flow-weighted concentration rollups or distinguish "how it was written" from "how to roll it up" |
| D7 | Derived variables: **data-driven linear recipes** (compiled from MASS-LINK/SCHEMATIC) **+ registered code transforms** (GENER, non-linear) — both versioned | A flat multiplier table can't express GENER/chained logic; a universal expression DSL in a table is a worse programming language. Hybrid covers both cleanly |
| D8 | **Catalog lives in the lake** as Parquet, published like data; any local DuckDB file is a disposable build cache | No service allowed on the share; single authority for `run_id` assignment; DuckDB remains the local compute engine |
| D9 | **Publish protocol**: single writer, stage → validate → atomic rename, per-run `manifest.json`, append-only with deprecation flags | "Parquet is read-only" protects readers from each other, not from the writer; SMB needs explicit discipline |
| D10 | UCI parameters stay **long (EAV)** in the catalog; wide views are curated/BI artifacts | Parameter space is sparse and heterogeneous per operation type; EAV is schema-change-proof |
| D11 | The **Python client API is the public contract**, not folder paths | Lets the physical layout evolve; BI reads curated marts, scripts use the API |
| D12 | Timestamps normalized to **period-start labels** with the convention recorded in manifests; raw keeps **engine-native units**, conversions happen only in curated | Prevents silent misalignment across resolutions and against observations; prevents double conversion |

## 4. Architecture overview

```
UCI / HBN / WDM files                      (per model run, on workstations)
        │
        │  parse (model layer: uci.py, hbn.py, wdm.py, parser/)
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ INGEST + VALIDATE (pipeline, runs locally, single writer)       │
│  · assign run_id · extract base-resolution series               │
│  · cross-resolution & mass-balance gates · write manifest       │
└──────┬──────────────────────────────────────────┬───────────────┘
       ▼                                          ▼
┌────────────────────┐                 ┌──────────────────────────┐
│ RAW TIER           │                 │ CATALOG                  │
│ immutable Parquet  │                 │ in-lake Parquet          │
│ wide-per-block     │                 │ runs · entities · lexicon│
│ base resolution    │                 │ series map · recipes     │
│ engine units       │                 │ transforms · edges       │
│ partition: run_id  │                 │ gauge map · UCI EAV      │
└──────┬─────────────┘                 └──────┬───────────────────┘
       │              versioned code          │
       └───────────────► CURATED BUILDERS ◄───┘
                        (refactored reports/*)
                               │
                               ▼
                  ┌──────────────────────────┐
                  │ CURATED TIER             │
                  │ disposable, reproducible │
                  │ derived vars · rollups   │
                  │ BI marts · releases      │
                  └──────┬───────────────────┘
                         ▼
   Tableau / Power BI (curated only) · Python API (raw + curated)
   Local calibration workbench (same schemas, local disk, promoted on bless)
```

### 4.1 Raw tier

Exactly what the engine produced, at the highest resolution it produced, in native
units. Written once per run, never edited, never deleted (deprecated via catalog
flag). If a raw file is wrong, the *run* was wrong — re-run and publish a new
`run_id`.

### 4.2 Catalog

The semantic layer, stored as small Parquet files in the lake and published with the
same discipline as data. It answers: what runs exist, what entities they contain,
what each variable means, how each stored series was produced and should be
aggregated, how derived variables are computed, and how water routes.

### 4.3 Curated tier

Everything a consumer actually wants that is not raw: TP/TN and other derived
series, monthly/annual rollups, catchment/watershed loading marts, long-format BI
extracts, wide UCI parameter views. **Disposable by construction** — regenerated
deterministically from raw + catalog by versioned builder code. Fixing a recipe means
bumping the recipe, rebuilding curated, publishing a new release; raw is untouched.

### 4.4 Consumption

- **BI tools** read curated marts only (shaped for the dashboard: long format where
  needed, pre-joined dimensions, pre-aggregated where sensible).
- **Python users** go through the client API (`lake.timeseries(...)`,
  `lake.derived(...)`, `lake.loading(...)`), which hides folder layout and applies
  catalog semantics.
- **Nobody** writes to the share except the publisher pipeline.

### 4.5 Local workbench (calibration)

Same table shapes, different lifecycle: a scratch area (local disk, DuckDB) holding
iterative runs during calibration. Promotion = running the standard publish pipeline
on the blessed run. One mental model, one codebase, no MLflow/SQLite detour.

## 5. Physical layout

```
\\server\share\hspf_lake\
├── raw\
│   └── run_id=r2026q3_bigfork\
│       ├── manifest.json
│       ├── block=perlnd_pwater\timestep=monthly\part-0.parquet
│       ├── block=rchres_hydr\timestep=hourly\year=1998\part-0.parquet
│       └── ...
├── catalog\
│   ├── runs.parquet            entities.parquet        variables.parquet
│   ├── series_map.parquet      recipes.parquet         transforms.parquet
│   ├── edges.parquet           gauges.parquet          releases.parquet
│   └── uci\parameters.parquet  flags.parquet  properties.parquet  ftables.parquet
├── curated\
│   ├── v=2026-08-13a\
│   │   ├── mart=derived_timeseries\...
│   │   ├── mart=loading\...
│   │   ├── mart=rollups\...
│   │   └── mart=bi_long\...
│   ├── v=2026-07-02\...
│   └── CURRENT.txt             ← pointer file naming the active release
└── observations\
    └── provider=usgs\...       (peer of raw, same shapes, gauge entities)
```

Layout rules:

- **Hive-style partition keys** (`run_id=`, `block=`, `timestep=`, `year=` for hourly
  only) so DuckDB/pyarrow/Power BI folder ingestion recover keys from paths. Partition
  keys are *also* materialized as columns inside files (they RLE-compress to nothing)
  so a file copied out of the tree keeps its identity.
- **Fewer, larger files.** Do not partition monthly data by year or anything by
  entity. Target 100 MB–1 GB per file; sort rows by `entity_id, timestamp` so row-group
  statistics do the pruning. On SMB, file-open overhead dominates — this matters more
  than on S3.
- **UNC paths only** in catalogs and manifests; never drive letters.
- `block` = `entitytype_activity` (e.g. `perlnd_pwater`, `perlnd_sedmnt`,
  `implnd_iwater`, `rchres_hydr`, `rchres_gqual`). Columns within a block are that
  activity's variables; grain is `(entity_id, timestamp)`. Schema may differ across
  runs within a block (different BINARY-INFO configs); readers must use
  schema-unifying scans (`union_by_name`), and ingest records each file's exact
  schema in the manifest.

## 6. Data model

### 6.1 Run identity (catalog: `runs`)

| Column | Notes |
|---|---|
| `run_id` | Surrogate key, assigned by the publisher. Human-scannable form is fine (`r20260813_0922_bigfork`) as long as **nothing parses it** |
| `model_name` | Stable geographic identity (e.g. `bigfork`); joins to entities, gauges, edges |
| `run_timestamp`, `execution_user` | Who/when published |
| `sim_start`, `sim_end` | From GLOBAL block; universal + filter-heavy ⇒ core columns |
| `unit_system` | From GLOBAL `EMFG` (1 = English, 2 = Metric — manual, GLOBAL block). Per-operation GEN-INFO `IUNITS`/`OUNITS` deviations are an entity/series-level concern (Phase 3), not a run column |
| `engine_version`, `schema_version`, `pipeline_git_hash` | Reproducibility |
| `source_uci`, `source_hbns` | Pointers (UNC) to inputs for audit |
| `status` | `active` \| `deprecated` \| `superseded_by:<run_id>` — files are never deleted |
| `attributes` | JSON string: scenario, version, land-use year, climate, calibration phase, HUC8 list, notes… — the flex bucket |

Core-vs-flex rule: *identity, relationship, or time ⇒ column; characteristics,
tweaks, nuance ⇒ attributes.* `model_year` is an attribute of the run (derived from
GLOBAL), **not** part of identity — this corrects the current
`(model_name, model_year, run_id)` composite key in `sql/schema.sql`.

### 6.2 Entities (catalog: `entities`)

Keyed by `(run_id, entity_type, entity_id)` because operations can change between
runs. Carries description, area, land-cover class, met zone, and reach attributes.
Sourced from OPN SEQUENCE + SCHEMATIC + land-use mapping seeds
(`data/LandUseNames_Mappings.csv`, `data/model_landcovers.csv`).

### 6.3 Variable lexicon (catalog: `variables`)

Run-independent dictionary keyed by `(entity_type, activity, variable)`: description,
native unit, the member-name decomposition (`base_member` + `qualifier` — HBN names
are compositional, e.g. `POQUAL` + `NH3+NH4` → `POQUALNH3+NH4`; the verbatim name is
preserved, the decomposition lets one row describe a member across QUAL configs),
two **orthogonal** kind columns, and **default** `aggregate_by` and
`weight_variable`. Seeded from the existing `data/Timeseries Catalog` and parser
metadata.

The two kind columns must not be conflated into one:

- **`temporal_semantics`** — HSPF's own taxonomy (manual, DSS data types):
  point-instantaneous (`INST-VAL`), mean-average (`PER-AVER`), mean-total
  (`PER-CUM`). Manual-derivable per variable; mechanically drives `produced_as`
  defaults and the gate-1 reducers (PER-CUM → sum, PER-AVER → mean, INST-VAL → last).
- **`physical_kind`** — our classification (`flux` | `state` | `concentration` |
  `temperature` …); drives curated weighting choices and sanity thresholds.

One axis cannot encode both: concentrations are PER-AVER and storages INST-VAL, but
temperature is PER-AVER while stage height is INST-VAL.

**Companion registry (catalog: `constituents`)** — the lexicon is
run-independent, but user-named generic constituents (PQUAL/IQUAL `QUALID`,
GQUAL `GQID`, CONS `CONID`) have identity only per model configuration: the
manual establishes them positionally (the Nth QUAL-PROPS table group defines
QUAL #N) and the HBN composes member names from them (`POQUAL` + `ORTHO P` →
`POQUALORTHO P`). A per-run registry `(run_id, entity_type, activity,
slot_index, constituent_id, quantity_units, association flags)` is compiled
from the UCI and cross-checked against actual HBN member names at publish.
The lexicon holds base members; the registry binds qualifiers per run.
Fixed-species identities (NUTRX NO3/TAM/NO2/PO4, sediment sand/silt/clay,
PLANK organics, OXRX DOX/BOD) need no registry — their subscript positions
are HSPF constants, kept as core vocabulary (`core\constituents.py`).

**Transport roles and phases** — HSPF's transport model has three roles, and
the vocabulary keeps them distinct: water and sediment are *carriers*;
chemical species and heat are *transported substances*; flow, sediment, and
water temperature double as calibration targets (`TransportRole.DUAL`).
Substances bind to carriers through *phases/associations* — dissolved vs.
particulate-by-sediment-fraction in reaches (NUIF1 vs. NUIF2), and the
QUAL-PROPS association flags on land (QSOFG/QIFWFG/QAGWFG/QSDFG →
`PathwayAssociation`). `core\constituents.py` owns this vocabulary
(`TransportRole`, `Phase`, `PathwayAssociation`, `SubstancePhase`). Downstream
it is what makes `weight_variable` defaults *derivable* (intensive variables
weight by their carrier's flux — concentrations by flow, sediment-associated
concentrations by sediment flux), gives gate 2 its separate water/sediment/
substance ledgers, keys recipe terms, and maps gauge observables to the model
phases that sum to them (Phase 6: observed whole-water TP = dissolved +
particulate + organic phases).

### 6.4 Series map (catalog: `series_map`) — provenance ≠ aggregation

For every stored series: `run_id`, `block`, `variable`, `timestep`, plus two distinct
semantic fields:

- **`produced_as`** — how the engine wrote the stored values, in the
  transformation-function vocabulary (`SUM` ↔ PER-CUM, `AVER` ↔ PER-AVER,
  `LAST` ↔ INST-VAL), parsed from BINARY-INFO / EXT TARGETS. Where the EXT
  TARGETS `TRAN` field is blank the effective function is the manual's
  **kind-dependent default** (SAME/AVER/SUM/DIV/INTP/LAST, selected by interval
  relation × point/mean kinds — manual, EXT SOURCES/TARGETS transformation
  table); the compiler resolves blanks through that rule table using the
  lexicon's `temporal_semantics` and never copies the raw column as-is. Needed
  to *interpret* raw correctly.
- **`aggregate_by`** (+ **`weight_variable`**) — how to roll it up further
  (`SUM`, `LAST`, `MEAN`, `WEIGHTED_MEAN(weight=…)`). Concentrations roll up
  flow-weighted; the weight series must exist at the same resolution — ingest
  enforces this.

Plus the resolved time geometry, because level codes identify resolution
*classes*, not durations:

- **`interval_minutes`** — for level-2 (interval) series, INDELT (OPN SEQUENCE)
  × PIVL (BINARY-INFO); the manual defines level 2 as "every PIVL intervals"
  and INDELT spans 1 minute–1 day, so "hourly" is a per-run fact to record, not
  an enum fact to assume.
- **`pyrend`** — for yearly series, the month ending the printout year
  (water-year support); calendar-year semantics only when PYREND = 12.

Stored sparsely: defaults come from the lexicon; `series_map` rows are written only
where a run/entity range genuinely deviates (an entity-level override column is
nullable). This avoids materializing ~5.4 M mostly-identical rows while still
capturing HSPF's per-operation flexibility.

### 6.5 Derived variables — hybrid recipes (catalog: `recipes` + `transforms`)

- **`recipes`** — linear combinations compiled from MASS-LINK (× SCHEMATIC `AFACTR`
  where applicable): `(derived_variable, run_id, entity_type, entity_id?, term_order,
  source_block, source_variable, factor, source_ref)`. Covers TP/TN-style sums of
  proportions. Generated by a compiler, never hand-edited. The compiler
  interprets MASS-LINK `TMEMN`/`TMEMSB` through the fixed-species subscript
  layouts in `core\constituents.py` (`NUIF1` subscript 4 = dissolved PO4 is a
  manual constant, named rather than assumed) and reads BOD → N/P
  stoichiometric conversions from each run's `CONV-VAL1` parameters (`CVBO`,
  `CVBPC`, `CVBPN`, `BPCNTC`) — they are calibration parameters, never frozen
  constants. Recipe terms are keyed by typed `(substance, phase, fraction)`
  triples (`core\constituents.SubstancePhase`), not ad-hoc string names.
- **`transforms`** — registry of **code** derivations for everything a linear table
  can't express (GENER chains, non-linear logic): `(name, version, description,
  code_ref, input_signature, output_signature)`. The code lives in the curated-builder
  package; the registry makes it discoverable and versioned.

Every curated artifact records which recipe versions / transform versions produced
it (via the release manifest), so any number is traceable to exact logic.

### 6.6 Topology (catalog: `edges`) and observations (catalog: `gauges`)

- `edges`: unified edge list from SCHEMATIC + NETWORK + manual cross-model links:
  `(run_id, source_type, source_id, target_type, target_id, factor, link_kind,
  target_run_id?)`. SCHEMATIC and NETWORK are the same concept (directed edges) and
  are unioned, with `link_kind` preserving origin. This is the substrate for the
  existing `parser/graph.py` traversals and for cross-model trace-back.
- `gauges`: gauge↔reach mapping at `model_name` level: `(model_name, entity_type,
  entity_id, gauge_id, provider, drainage_area_ratio, datum/unit notes, qc_flags)`.
  Observation series live under `observations/` using the same wide shapes, with
  gauges as entities — peers of model runs, never mixed into them.

### 6.7 UCI parameters (catalog: `uci/*`)

The existing EAV design is kept as-is conceptually: `parameters`, `flags`,
`properties` keyed by `(run_id, operation_type, operation_id, table_name, name)`,
plus `ftables`. Wide per-operation-type views (`perlnd_params`, `rchres_params`, …)
are **curated artifacts**, pivoted at build time for BI — long for storage, wide for
serving.

### 6.8 Manifests

`raw/run_id=…/manifest.json`, written last (its presence marks the run complete):
file list with row counts + checksums + per-file schema hash, timestamp convention,
unit system, source file fingerprints (path, size, mtime, hash), pipeline git hash,
validation results summary, publish timestamp. `catalog/releases.parquet` plays the
same role for curated releases (input run set, builder versions, git hash).

## 7. Publish protocol (governance)

1. **Single writer.** Exactly one pipeline identity (person or scheduled job) writes
   to the lake. Everyone else mounts it read-only.
2. **Stage → validate → swap.** Write to `_staging\<target>` on the *same volume*,
   run validation gates, then directory-rename into place. Never write in place.
3. **Manifest-last.** Readers (and the client API) treat a run without a manifest as
   nonexistent. This makes partially-copied runs invisible instead of wrong.
4. **Append-only.** Runs are never overwritten or deleted; corrections are new runs
   with `status` updates (`deprecated`, `superseded_by`) in the catalog.
5. **Versioned curated releases.** Each rebuild writes `curated\v=<release>\`;
   `CURRENT.txt` is updated last (single small-file write). Dashboards either pin a
   release or resolve `CURRENT.txt` at refresh. Old releases are retained N versions.
6. **Catalog updates ship with the data that motivated them,** in the same publish
   operation — the anti-drift rule. A run's raw files and its catalog rows appear
   together or not at all.

## 8. Validation gates (ingest-time, publish-blocking)

The engine's habit of writing the same variable at multiple resolutions is a free QA
oracle — exploit it before dropping the redundant series:

1. **Cross-resolution consistency:** recompute monthly from daily/hourly using
   `produced_as` semantics; compare to the engine's own monthly within tolerance.
   Catches wrong aggregation rules immediately, at ingest, not in a dashboard.
2. **Mass balance:** area-weighted PERLND/IMPLND outflows (× SCHEMATIC factors) vs
   RCHRES inflows within tolerance.
3. **Coverage:** every series spans `sim_start..sim_end` at its timestep, no gaps,
   no duplicate timestamps, and observed spacing equals the declared interval
   (`interval_minutes` = INDELT × PIVL for level-2 series — catches the
   "tcode 2 assumed hourly" failure at ingest).
4. **Schema conformance:** every column resolves against the lexicon; unknown
   variables fail loudly (new variables are added to the lexicon deliberately).
5. **Referential integrity:** recipes reference existing series; edges reference
   existing entities; weight variables exist at the required resolution.
6. **Sanity:** NaN/negative-value thresholds per variable kind, entity counts match
   OPN SEQUENCE.

Failures block the publish. A validation summary lands in the manifest either way.

## 9. Conventions

Conventions are the *rules* of the system, as `core\types.py` is its *nouns*: the
small set of policies every tier must agree on for frames produced in one layer to
be interpretable in another. They are encoded once in `core\conventions.py`
(constants + small pure helpers, no I/O, no model/lake imports) and every manifest
records the conventions in force when its run was published — so a reader never
guesses what a stored timestamp or value means. Rationale is recorded here so the
code can stay terse.

### 9.1 Timestamps

- **Native HSPF labeling is end-of-interval.** The engine's day runs 00:00–24:00
  and point-valued series are "instantaneous at end of interval" (manual, DSS data
  types). The lake normalizes all raw series to **period-start** labels at ingest
  and stamps `timestamp_convention` into every manifest. All tiers, all
  resolutions, one rule — period-start is what BI time axes, resampling, and
  gauge-observation alignment expect. The model layer keeps native labels
  (Phase 1 is byte-identical; goldens pin current behavior).
- **Interval-level durations are per-run facts, not enum facts.** Output level 2
  means "every PIVL intervals", i.e. PIVL × INDELT minutes (manual, PRINT-INFO /
  BINARY-INFO explanation); INDELT may be any of 19 steps from 1 minute to 1 day.
  The period-start shift for level-2 series therefore takes a *resolved duration*
  argument — it never assumes hourly. Ingest records `interval_minutes` per
  series and gate 3 validates observed spacing against it.
- **Yearly series may be water years.** PYREND sets the month terminating the
  printout year (manual, PRINT-INFO); calendar-year normalization is valid only
  when PYREND = 12. Ingest reads PYREND per operation, records it in the series
  map, and treats non-calendar years by their recorded boundary.
- **Timestamps are timezone-naive model-local time.** HSPF has no timezone or DST
  concept; the lake never localizes model output. Observation ingest (Phase 6)
  converts gauge data *to* naive model-local time before alignment — model data
  is never converted toward the observations.

### 9.2 Units and values

- **Raw = engine-native, always.** `unit_system` is captured per run from GLOBAL
  `EMFG` (1 = English, 2 = Metric) at registration; per-operation GEN-INFO
  `IUNITS`/`OUNITS` deviations are captured at the entity/series level (Phase 3);
  per-variable native units live in the lexicon. Conversions occur only in
  curated builders, driven by lexicon metadata. No unit conversion at ingest,
  ever — one conversion point means no double-converted numbers and raw stays
  replay-identical to the engine.
- **Native precision is preserved.** HBN values are 4-byte floats; ingest writes
  them as such — no up-casting that fabricates precision, no rounding.

### 9.3 Naming

- `snake_case` table/column names in catalog and curated tiers (BI- and
  SQL-safe, grep-safe).
- Raw preserves HSPF variable names **verbatim** — including `+`, spaces, and
  embedded qualifiers (`POQUALNH3+NH4`, `SOQUALORTHO P`). They are the domain
  vocabulary and must round-trip through Parquet unchanged. Member names are
  compositional (base member + constituent qualifier); the *decomposition* is
  lexicon data (§6.3), the *anti-normalization rule* is a convention.
- The `run_id` grammar (generation + validation) lives in conventions; nothing
  downstream ever parses a run id back apart.
- The **house PERLND opnid grammar** (opnid encodes metzone + landcover —
  today's `decompose_perlands`) is likewise a recorded identifier convention:
  house-specific, superseded by the entities catalog (Phase 3), and validated
  against it once both exist. Structure encoded in identifiers must always
  have a catalog column as ground truth.

### 9.4 Paths

- UNC in all stored metadata; never drive letters — manifests must resolve
  identically from any machine that mounts the share.
- Relative paths within a run folder — a run directory is relocatable as a unit.

## 10. Target package layout

Current package strengths stay where they are: UCI/HBN/WDM parsing is mature and
becomes the *model layer*. The refactor is mostly **relocation plus purification**
(splitting I/O from transforms), not rewrites.

```
src\hspf\
├── core\                      # shared vocabulary, no I/O
│   ├── types.py               # shared vocabulary: TimeStep (HSPF output levels),
│   │                          #   OperationType vs EntityType, Activity + Block,
│   │                          #   EntityRef, RunRef, TemporalSemantics,
│   │                          #   TransformFunction, UnitSystem
│   ├── conventions.py         # the rules of §9: timestamp/unit/naming/path/run-id
│   ├── constituents.py        # substance & transport vocabulary: fixed-species
│   │                          #   enums, member subscript layouts, phases/roles,
│   │                          #   reporting constituents
│   ├── errors.py              # shared failure vocabulary (convention/gate errors)
│   └── util.py                # residual date helpers (dissolves by Phase 5)
│
├── model\                     # engine-facing: parse, edit, run (existing strength)
│   ├── uci.py                 # UCI class (read/edit/write/templates)
│   ├── hbn.py                 # hbnClass + hbnInterface (binary readers)
│   ├── wdm.py                 # wdmInterface / WDM readers (+ wdmReader.py merged)
│   ├── runner.py              # run_model, run_batch_files (from hspfModel.py, uci._run)
│   ├── session.py             # hspfModel facade (validate paths, load uci/hbn/wdm)
│   ├── parser\                # parsers.py, ParseTable-driven fixed-width parsing
│   └── graph.py               # UCI→networkx construction + traversals (from parser\graph.py)
│
├── lake\                      # the data lake: layout, catalog, ingest, publish
│   ├── layout.py              # path scheme, partition keys, UNC handling
│   ├── manifest.py            # manifest read/write/verify
│   ├── catalog\
│   │   ├── runs.py            # run registration, status transitions (from build_warehouse.build_model_table)
│   │   ├── entities.py        # entity extraction (OPN SEQUENCE + SCHEMATIC + seeds)
│   │   ├── lexicon.py         # variable dictionary (seeded from data\Timeseries Catalog)
│   │   ├── constituents.py    # per-run QUAL/GQUAL/CONS registry (slot → ID bindings)
│   │   ├── series_map.py      # provenance/aggregation compiler (BINARY-INFO, EXT TARGETS)
│   │   ├── recipes.py         # MASS-LINK×SCHEMATIC → linear recipe compiler
│   │   ├── transforms.py      # registry of code-based derivations
│   │   ├── edges.py           # SCHEMATIC+NETWORK+cross-model → edge list (uses model.graph)
│   │   ├── gauges.py          # gauge↔reach mapping
│   │   └── uci_tables.py      # EAV params/flags/props + ftables (from build_warehouse.build_parameter_table etc.)
│   ├── ingest.py              # HBN → raw parquet (base resolution, wide-per-block)
│   ├── validate.py            # §8 gates
│   ├── publish.py             # stage→validate→swap, single-writer lock, releases
│   └── duck.py                # local DuckDB build-cache helpers (from warehouse.py)
│
├── curated\                   # versioned builders: raw + catalog → marts
│   ├── build.py               # release orchestration (what to build, in what order)
│   ├── derive.py              # recipe/transform execution (TP, TN, …)
│   ├── rollups.py             # timestep rollups honoring aggregate_by/weights
│   ├── marts\
│   │   ├── loading.py         # from reports\loading.py (pure: frames in → frames out)
│   │   ├── yields.py          # from reports\yields.py
│   │   ├── nutrients.py       # from reports\nutrients.py
│   │   ├── sediment.py        # from reports\sediment.py
│   │   ├── hydrology.py       # from reports\hydrology.py
│   │   ├── contributions.py   # from reports\contributions.py
│   │   ├── residence.py       # from reports\residence.py
│   │   └── gener.py           # from reports\gener.py, registered as transforms
│   └── bi.py                  # long-format extracts, wide UCI param views
│
├── api\                       # the public contract
│   ├── reader.py              # Lake class: timeseries(), derived(), loading(), runs()…
│   └── xr.py                  # xarray adapters (from xarray_utils.py)
│
├── workbench\                 # calibration tier (later phase)
│   └── scratch.py             # local lake with identical schemas + promote()
│
├── data\                      # seeds for the catalog (unchanged location)
│   ├── ParseTable.csv, HSPFParameterRanges.csv,
│   ├── LandUseNames_Mappings.csv, model_landcovers.csv, Timeseries Catalog\
├── bin\WinHSPFLt\             # engine (unchanged)
└── legacy\                    # thin adapters for the old API during migration
    └── reports.py, outputs.py # delegate to curated.* / api.*, emit DeprecationWarning
```

### Module disposition map

| Existing | Target | Disposition |
|---|---|---|
| `uci.py` | `model\uci.py` (+ run bits → `model\runner.py`) | Move; split run/exec concerns out of the UCI class |
| `parser\parsers.py` | `model\parser\` | Move unchanged |
| `parser\graph.py` | `model\graph.py` + `lake\catalog\edges.py` | Split: construction/traversal stays model-side; persisted global edge list becomes a catalog compiler |
| `hbn.py` | `model\hbn.py`; module-level `get_simulated_*` → `curated\marts\` or `legacy\` | Split: readers stay; convenience transforms migrate to builders |
| `wdm.py`, `wdmReader.py` | `model\wdm.py` | Merge; also feeds `observations/` ingest |
| `hspfModel.py` | `model\session.py` + `model\runner.py` | Split facade vs execution |
| `build_warehouse.py` | `lake\catalog\*` (runs, uci_tables, edges…) | Split by catalog table; `model_year`-in-key corrected to run attribute |
| `warehouse.py` | `lake\duck.py` | Move; role reframed as local build cache, not system of record |
| `sql\schema.sql` | `lake\schemas\` (versioned schema contracts) | Rework: catalog/raw/curated contracts + `schema_version` |
| `outputs.py` | `legacy\outputs.py` | Deprecate; replaced by curated marts + API |
| `reports\*` | `curated\marts\*` (+ `legacy\reports.py` shim) | Refactor to pure transforms: `(uci, hbn)` args become raw frames + catalog frames; **this is the core refactor axis** |
| `xarray_utils.py` | `api\xr.py` (+ `TimeStep` → `core\types.py`) | Move; enum promoted to shared core |
| `helpers.py` | `core\constituents.py` + `core\conventions.py` + `core\util.py` | Split: substance vocabulary / house opnid grammar / residual date helpers |
| `data\*` | `data\` (as catalog seeds) | Keep; formalized as lexicon/mapping seed inputs |

The dependency rule between layers is one-directional:
`core ← model ← lake ← curated ← api` (and `workbench` uses `lake`+`curated`).
Nothing in `model\` may import from `lake\` or below; nothing in `curated\` may read
HBN/UCI files directly — it sees only raw + catalog frames. That rule is what makes
curated rebuildable and testable.

## 11. Migration plan

Phased so the current workflow keeps working throughout; each phase lands value on
its own. Detailed file-level implementation guidance for each phase lives in
[implementation_plan.md](implementation_plan.md).

- **Phase 0 — Characterize.** Pick 2–3 representative models; snapshot current
  `reports\*` outputs as golden fixtures in `tests\`. These anchor every later phase.
- **Phase 1 — Core + model layer.** Create `core\` (output-level/TimeStep enum,
  operation + block taxonomy, temporal-semantics vocabulary, substance &
  transport vocabulary, conventions, shared error types) and
  reorganize `uci/hbn/wdm/parser/graph` into `model\` with shims at
  old import paths. No behavior change.
- **Phase 2 — Lake foundation.** `layout`, `manifest`, `ingest` (HBN → raw
  wide-per-block), `runs` catalog, validation gates 3/4/6, `publish` with staging +
  atomic swap. Outcome: immutable raw tier on the share for new runs.
- **Phase 3 — Semantics.** Lexicon seeded from `data\Timeseries Catalog`;
  `series_map` compiler (enables gate 1, cross-resolution); `recipes` compiler from
  MASS-LINK/SCHEMATIC (validated against the existing on-the-fly TP calculation);
  `edges`, `gauges`, `uci_tables`, and the per-run constituent registry
  (QUAL/GQUAL/CONS bindings). Outcome: the lake is self-describing.
- **Phase 4 — Curated builders.** Port `reports\loading.py` first (largest user
  value), validating each mart against Phase-0 goldens; then rollups/derive and the
  remaining marts; `releases` + `CURRENT.txt`. Outcome: BI switches to curated.
- **Phase 5 — API + cutover.** `api\reader.py` as the supported entry point;
  `legacy\` shims with deprecation warnings; docs. Backfill the 68 models by batch
  ingest. Outcome: old paths retired.
- **Phase 6 — Workbench + observations (optional, as needed).** Local scratch lake
  with `promote()`; USGS/observation ingest into `observations\` with gauge mapping.

## 12. Extension points

- **Cloud scale-up:** the lake is a folder of Parquet + manifests — relocating to S3
  and pointing Athena/Trino at it is a move, not a rewrite (D1, D8).
- **New derived variables:** add a recipe row or register a transform; rebuild
  curated. No raw changes (D7).
- **New experiment dimensions:** new keys in `runs.attributes`; no schema change (D5).
- **Model-to-model linkage analyses:** `edges` with `target_run_id` already spans
  models; graph tooling consumes it directly (D6.6).
- **A real metadata DB later:** the catalog schema maps 1:1 onto PostgreSQL if the
  agency ever allows a server; Parquet catalog remains the interchange format.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Metadata drift (raw updated, catalog stale) | Single publish operation ships both (§7.6); manifests cross-check |
| Writer/reader collision on SMB | Staging + rename swap, manifest-last, versioned curated releases (§7) |
| Wrong aggregation silently poisoning rollups | Cross-resolution oracle gate at ingest (§8.1) |
| Recipe errors (MASS-LINK misread) | Recipes compiled + validated against legacy on-the-fly results in Phase 3; versioned, traceable via releases |
| Schema drift across runs within a block | `union_by_name` reads, per-file schema hashes in manifests, lexicon conformance gate |
| Curated/legacy divergence during migration | Golden fixtures from Phase 0 gate every mart port |
| Single-writer bottleneck | Acceptable at agency cadence (runs are milestone events, not daily); revisit only if cadence changes |

## 14. Open questions

1. `run_id` format: timestamp-based human-scannable vs opaque UUID (recommend the
   former; either is fine because nothing parses it).
2. Curated release retention: how many versions to keep on the share (recommend 3).
3. Hourly tier: partition by `year=` always, or only when a block exceeds ~1 GB
   (recommend the latter, decided by ingest automatically).
4. Do BI dashboards pin releases or follow `CURRENT.txt`? (recommend follow, with
   pinning available for published reports.)
5. Whether `observations\` ingestion is in scope for the first backfill or deferred
   to Phase 6.

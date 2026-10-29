# Constituent Crosswalk — Hub-and-Spoke Design

**Status:** Proposal
**Scope:** Ownership and structure of the constituent vocabularies across `hspf` (pyHSPF),
`mpcaHydro`, and `pyhcal`: who defines what, what new code is written in each package,
and how agreement is enforced without cross-imports.

Companion documents:
- `evaluation_schema.md` — the tables whose `constituent` column uses the hub vocabulary
- `pest_architecture.md` — layering rules this design must respect

---

## 1. The problem

Three vocabularies describe "the same stuff":

1. **HSPF output lexicon** (pyHSPF): `SSEDTOT`, `PTOTCONC`, `TAMCONCDIS`, `ROVOL`,
   `POQUALNO3`, … — hundreds of variable names, per operation type, with member/subscript
   encodings (`NUIF2 (2,2)` = particulate PO4 on silt).
2. **Data-collection lexicon** (mpcaHydro): EQuIS lab parameter codes, WISKI timeseries
   names, result units, detection limits, qualifiers.
3. **Reporting lexicon** (everyone): `TSS`, `TP`, `OP`, `N`, `TKN`, `TN`, `Q`, `WT`,
   `DO`, `ChlA`, `BOD` — what appears in reports, configs, dashboards, and conversation.

A direct HSPF ↔ collection mapping forces whichever package owns it to know the other's
internals, inverting the layering (pyHSPF must stay a general HSPF library; mpcaHydro
must stay a data-access library — neither may import the other).

## 2. The resolution: a hub with two spokes

**No direct mapping exists.** Both specialized lexicons map into the small neutral
reporting vocabulary — the **hub** — and the "crosswalk" between HSPF and collection
codes exists only as a *composition through the hub*, computed where both packages are
available (pyhcal).

```
mpcaHydro lexicon ──(spoke B: mpcaHydro owns)──►  HUB  ◄──(spoke A: pyhspf owns)── HSPF lexicon
EQuIS 00530, WISKI Q.day …                     TSS, TP, Q …              SSEDTOT, PTOTCONC, ROVOL …
                                                ▲
                                                │ (joins + conformance test)
                                              pyhcal
```

| Piece | Owner | Depends on |
|---|---|---|
| Hub vocabulary (names + semantics) | **pyhspf defines it physically; everyone honors it as a contract** | nothing |
| Spoke A: HSPF variables → hub | **pyhspf** | hspf only |
| Spoke B: collection parameters → hub | **mpcaHydro** | mpcaHydro only |
| Composition ("what EQuIS code corresponds to SSEDTOT?") | **pyhcal**, computed on demand | both |
| Conformance enforcement | **pyhcal** (tests) | both |

### 2.1 Why the hub lives in pyhspf but is a *contract*, not an import

`ReportingConstituent` already exists in pyhspf's core types, and pyhspf needs it
standalone — "SSEDTOT is a TSS series" must be answerable with no observational data in
sight (your stated use case). So the authoritative definition stays there.

But mpcaHydro must **not** import pyhspf to use the names. Instead, the hub is treated as
a *convention*: mpcaHydro embeds its own copy of the hub table (plain strings), and
pyhcal — the only package that imports both — runs a conformance test asserting the two
copies agree. Deliberate duplication with automated agreement is cheaper and cleaner than
a shared micro-package or an upward dependency. (If a third consumer ever appears, the hub
can graduate into a tiny `mn-constituents` package; don't pay that tax now.)

### 2.2 What the hub actually contains

More than names — the hub record is the **semantic contract** per constituent:

| field | example (`TP`) | why it must be in the hub |
|---|---|---|
| `constituent` (key) | `TP` | join key everywhere |
| `display_name` | Total Phosphorus | reports/BI |
| `kind` | concentration-bearing | `VariableKind` vocabulary |
| `agg_method` | `MEAN` (conc) / `SUM` (load) | the mean-vs-sum switch currently buried in `metrics.aggregate` asserts |
| `units_conc` | `mg/L` | canonical comparison units |
| `units_load` | `lb/day` | " |
| `is_derived` / `derived_from` | `TP_load ← TP, Q`; `QB ← Q` | derivations are declared, not implied by string lists |

Both spokes must deliver series *already in canonical hub units with hub aggregation
semantics*. That single rule is what makes observed and simulated series directly
comparable no matter which adapter produced them.

---

## 3. New code, package by package

### 3.1 pyhspf (owns the hub + spoke A)

```
hspf/core/constituents.py        # NEW — the hub
hspf/core/constituent_map.py     # NEW — spoke A: hub → HBN variable terms
```

**`constituents.py` — the hub.** A frozen dataclass `Constituent` with the fields of
§2.2, a module-level registry (dict keyed by name, rows as data), and two helpers:
`get(name)`, `all_constituents()`. Absorbs and formalizes the existing
`ReportingConstituent` enum (the enum can remain as the key type). Also export the
registry as a DataFrame (`to_frame()`) — that is what populates the `constituents`
dimension in `evaluation_schema.md` and what the conformance test compares.

**`constituent_map.py` — spoke A.** Replaces `get_tcons()` / `nutrient_id()` /
`nutrient_name()` with *data rows + pure lookups*, in the same style as
`MEMBER_SUBSCRIPTS`:

- A row = `(constituent, entity_type, form, terms)` where `form` is
  `conc` | `load` | `flow` | `temp`, and `terms` is a tuple of
  `(hbn_variable, coefficient)` pairs. Signed terms make today's comment-encoded
  arithmetic explicit and auditable:
  - `TKN` conc @ RCHRES → `(TAMCONCDIS, +1), (NTOTORGCONC, +1)`
  - `N` conc @ RCHRES → `(NO2CONCDIS, +1), (NO3CONCDIS, +1)`
  - the legacy "TP is really BOD minus ortho-P" path → explicit `(…, +1), (…, −1)` terms
    instead of a comment nobody can test
- Lookup: `hbn_terms(constituent, entity_type, form) -> tuple[Term, ...]`, raising a
  clear error for undefined combinations.
- Validation (unit tests in pyhspf): every referenced HBN variable exists in the
  catalog vocabulary; every non-derived hub constituent has at least one RCHRES mapping;
  coefficients are nonzero.

**Deprecations:** `get_tcons`, `nutrient_id`, `nutrient_name` become thin wrappers over
the new lookups (with `DeprecationWarning`), then are removed once pyhcal migrates. The
legacy integer ids (`{0:'TSS', …}`) and the hardcoded
`{'N':1,'TKN':0,'OP':2,'TP':3}` table-id map in pyhcal's `update_qualprop` should both be
re-expressed as rows in this module — UCI table-id assignments are HSPF knowledge.

### 3.2 mpcaHydro (owns spoke B)

```
mpcaHydro/constituents.py        # NEW — mirrored hub table (plain strings, no imports)
mpcaHydro/constituent_map.py     # NEW — spoke B: collection params → hub
```

**`constituents.py` — the mirror.** The same hub rows as pyhspf's, as plain data
(dict/rows of strings — *no* import of hspf). It exists so mpcaHydro code can validate
and label its outputs independently. Drift between mirror and hub is caught by pyhcal's
conformance test, not by an import.

**`constituent_map.py` — spoke B.** Data rows + pure lookups mapping collection
identifiers to the hub:

- A row = `(origin, parameter_code_or_ts_name, source_unit)` →
  `(constituent, conversion_factor, form)` — e.g. EQuIS `00530` in `mg/L` → `TSS` conc,
  factor 1.0; WISKI daily discharge in `cfs` → `Q` flow.
- Policy knowledge that belongs *only* here: which lab codes roll up into a reporting
  constituent, unit conversions into canonical hub units, detection-limit/qualifier
  handling defaults.
- Public functions:
  - `to_reporting(raw_df) -> tidy df` — warehouse rows in, hub-labeled series out
    (hub names, canonical units, `agg_method` honored). The existing data-manager
    retrieval paths route through this so **everything mpcaHydro serves is already
    hub-labeled** — pyhcal never sees a lab code.
  - `inventory(stations, constituent) -> record` — computed data-availability summary
    (replaces the stale `Observation` metadata fields in the old calibration config).

### 3.3 pyhcal (owns the join + enforcement; writes **no mapping data**)

```
src/pyhcal/evaluation/sources.py         # adapters call the spokes (see evaluation_schema.md §4)
tests/test_constituent_conformance.py    # NEW — the enforcement
```

- **No crosswalk tables live here.** `HbnSource`/`LakeSource` resolve hub → HBN terms via
  `hspf.core.constituent_map.hbn_terms`; observed adapters receive already-hub-labeled
  data from mpcaHydro. Derived constituents (`TP_load = TP × Q`, `QB` via baseflow
  separation) are implemented once, in the transform registry, per the hub's
  `derived_from` declarations.
- **Conformance test** (the keystone of the whole design, ~50 lines):
  1. `hspf.core.constituents.to_frame()` equals `mpcaHydro.constituents.to_frame()`
     on the intersection of keys — names, units, `agg_method`, `kind` all identical;
  2. every constituent referenced by any calibration config resolves in *both* spokes
     (or is explicitly flagged sim-only / obs-only);
  3. every `derived_from` reference points at defined hub constituents.
  Because pyhcal already depends on both packages, this is the natural — and only —
  place the two mirrors can be compared.
- **Convenience composition** (nice-to-have): a `crosswalk(constituent)` helper returning
  the HSPF terms and collection codes side by side, for humans asking "what do we compare
  against SSEDTOT?" — computed, never stored.

### 3.4 Dependency rules (unchanged, now test-enforced)

| Rule | Enforced by |
|---|---|
| `hspf` imports neither `mpcaHydro` nor `pyhcal` | import-hygiene test in pyhspf |
| `mpcaHydro` imports neither `hspf` nor `pyhcal` | import-hygiene test in mpcaHydro |
| `pyhcal` imports both; owns all composition | conformance test above |
| Hub names/units/semantics identical in both mirrors | conformance test above |

---

## 4. Worked examples

**"Compare TP at the Nemadji outlet"** (evaluation engine, hub-only):
1. Config says `constituent: TP`, location → reach terms + stations.
2. `HbnSource` asks spoke A: `hbn_terms('TP', RCHRES, 'conc')` → `(PTOTCONC, +1)`;
   reads HBN, returns mg/L series.
3. `DuckdbObservedSource` returns the stations' pooled series — already hub-labeled
   mg/L because mpcaHydro's `to_reporting` ran at download time.
4. Engine joins, transforms, scores. No layer translated between lexicons at
   comparison time.

**"What's the data-collection equivalent of a model output?"** (your standalone use case):
`hspf` alone answers `SSEDTOT → TSS` (spoke A, reversed lookup) with no observational
dependencies. The full chain to EQuIS codes needs spoke B too, so *that* question is
answered in pyhcal via the `crosswalk()` helper — by composition, never by a stored
HSPF↔EQuIS table.

**"Add chlorophyll-a calibration"**: one hub row (`ChlA` — already present), spoke A rows
(PLANK variables → `ChlA`), spoke B rows (lab codes → `ChlA`). No pyhcal change at all —
configs may immediately reference `ChlA`, and the conformance test proves both sides are
ready.

---

## 5. Migration order

1. pyhspf: create `constituents.py` + `constituent_map.py`; wrap-and-deprecate
   `get_tcons`/`nutrient_*`; add validation tests.
2. mpcaHydro: create the mirror + spoke B; route the data-manager output through
   `to_reporting`; add `inventory()`.
3. pyhcal: add the conformance test; point `update_qualprop`'s table-id map and the
   evaluation adapters at the new lookups; delete local magic-string dicts as they fall
   out of use.

Each step is independently shippable; nothing breaks while legacy wrappers remain.

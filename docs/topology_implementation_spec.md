# Topology Builder: Technical Implementation Specification

**Status:** Implementation spec (companion to `edge_consolidation_plan.md`)
**Date:** 2026-09-30
**Audience:** The implementing programmer. Assumes familiarity with the
codebase; every type, function, and frame schema below is specified so the
work can proceed without re-deriving design decisions.

---

## Part 1 — What the three tables represent (with worked examples)

Before the code plan, the domain model. Getting this crisp is what makes the
builder's correctness checkable.

### 1.1 The two-layer design of HSPF connectivity

HSPF separates *who connects to whom* from *what is handed off*. The UCI
expresses connectivity through two alternative mechanisms:

```text
Mechanism A:  SCHEMATIC  ×  MASS-LINK     (connection + reusable recipe)
Mechanism B:  NETWORK                      (direct member-to-member wiring)
```

A model may use either or both. **Union of both = routing truth.**

### 1.2 SCHEMATIC: the connection grain

One SCHEMATIC row declares one *connection* between two operations, with a
scaling factor and a pointer to a recipe:

```text
<-Volume->                  <--Area-->     <-Volume->  <ML#>
<Name>   x        x         <-factor->     <Name>   x
PERLND 101                        42.7     RCHRES   5    2
PERLND 102                       118.3     RCHRES   5    2
PERLND 102                        55.0     RCHRES   6    2
RCHRES   5                         1.0     RCHRES   6    1
```

Reading row 1: *42.7 acres of PERLND 101 drain to RCHRES 5, transferring
quantities according to MASS-LINK 2.*

Key facts:

- `AFACTR` is **area** for land→reach rows (acres), a plain multiplier
  (usually 1.0) for reach→reach rows, and a **count** for GENER sources.
  This is why summing every `AFACTR` as "area" is wrong — the current
  `graph.py` bug noted in the review.
- The same PERLND may appear in multiple rows (102 above splits its acreage
  between RCHRES 5 and 6). A PERLND is a *lumped* unit; SCHEMATIC rows are
  how its area is apportioned. There is no "the" reach for a PERLND.
- A SCHEMATIC row says **nothing** about which quantities move. That is
  delegated to MASS-LINK via `MLNO`.
- `TMEMSB1/TMEMSB2` on a SCHEMATIC row, when present, **override** the
  target subscripts in the referenced MASS-LINK rows (used e.g. to direct
  inflow to a specific RCHRES exit/category).

### 1.3 MASS-LINK: the reusable recipe

A MASS-LINK table is a *template*, keyed by number, listing member-level
transfers. It deliberately omits operation ids — it applies to every
SCHEMATIC row that cites it:

```text
MASS-LINK        2
<-Volume-> <-Grp> <-Member-><--Mult-->     <-Target vols> <-Grp> <-Member->
PERLND     PWATER PERO      0.0833333      RCHRES         INFLOW IVOL
PERLND     SEDMNT SOSED     1.0            RCHRES         INFLOW ISED  3
PERLND     PQUAL  POQUAL  1  1.0           RCHRES         INFLOW IDQAL 1
  END MASS-LINK  2
```

Reading row 1: *take PERO (total outflow, inches) from PWATER, multiply by
0.0833333 (in → ft), deliver as IVOL into the target's INFLOW group.*

### 1.4 The join: SCHEMATIC × MASS-LINK = member transfers

The two combine on `(MLNO, SVOL, TVOL)`. Each SCHEMATIC row *fans out* into
one member-transfer row per matching MASS-LINK row:

```text
SCHEMATIC row                MASS-LINK 2 row            Resulting member transfer
──────────────────────────   ────────────────────────   ─────────────────────────────────
PERLND 101 → RCHRES 5      × PWATER PERO ×0.0833 → IVOL  = PERO→IVOL,  factor 42.7×0.0833
  AFACTR 42.7, MLNO 2      × SEDMNT SOSED ×1.0  → ISED   = SOSED→ISED, factor 42.7×1.0
                           × PQUAL POQUAL ×1.0  → IDQAL  = POQUAL→IDQAL, factor 42.7×1.0
```

So: **effective_factor = AFACTR × MFACTOR**. This works because PERLND
outputs are per-acre; multiplying by acres yields totals. The grain
relationship:

```text
1 SCHEMATIC row (connection)  →  N member-transfer rows (N = rows in its MASS-LINK)
```

Two hazards the builder must preserve as *data*, not hide:

- **Unmatched SCHEMATIC rows** (MLNO cites a missing/non-matching template):
  keep the connection row, flag `unmatched_schematic=True`. (Already done in
  `routing.py`'s left join.)
- **AFACTR repetition**: AFACTR repeats on each of the N member rows.
  Summing areas at member grain double-counts; area questions must be asked
  at connection grain. This is the reason two grains exist in the design.

### 1.5 NETWORK: the direct grain

One NETWORK row *is already* a member transfer — no template, no area:

```text
<-Volume-> <-Grp> <-Member-><--Mult-->Tran <-Target vols> <-Grp> <-Member->
RCHRES   5 HYDR   RO        1.0            RCHRES       6 EXTNL  IVOL
COPY     1 OUTPUT MEAN   1  1.0            PERLND 101 120 EXTNL  PREC
GENER    3 OUTPUT TIMSER    1.0       SAME RCHRES       9 EXTNL  IVOL
```

Differences from Mechanism A, all already handled in `routing.py`:

| Aspect | SCHEMATIC×MASS-LINK | NETWORK |
|---|---|---|
| Grain | connection, fans out via template | member transfer directly |
| Area | explicit `AFACTR` | none — folded invisibly into `MFACTOR` |
| Target id | single `TVOLNO` | `TOPFST`–`TOPLST` range, exploded **at parse time** (`expand_extsources`); the builder just renames `TOPFST → TVOLNO` |
| Recipe | `MLNO` reference | inline member fields + optional `TRAN` |
| effective_factor | AFACTR × MFACTOR | MFACTOR |

Consequences:

- A NETWORK land→reach transfer has **no recoverable acreage** — hence the
  `network_area_basis` flag in the U3 classification and the `area=NA` rule
  for NETWORK edges in the graph.
- Connection-grain rows for NETWORK are *derived* by grouping its member
  rows on (source op, target op).
- The same physical transfer declared in both mechanisms is double-counted
  flow — validation check U8's subject.

### 1.6 Are these three tables sufficient? (evaluation)

Verdict: **for internal routing connectivity, yes — SCHEMATIC, MASS-LINK,
NETWORK are the complete set.** HSPF has no other block that moves mass
between operations. But "connectivity" for your use cases is wider than
internal routing. Full survey of candidate UCI tables:

| Table | Connectivity role | Decision |
|---|---|---|
| `OPN SEQUENCE` | Defines the node universe (what runs) and execution order | **Required** — already the node source; keep as canonical set |
| `GEN-INFO` (per op type) | Node attributes: LSID, RCHID, `LKFG` (lake flag), `NEXITS` | **Required as node attributes** — LKFG drives lake classification; NEXITS bounds exit subscripts |
| `EXT SOURCES` | Boundary **inputs**: WDM DSN → operation member (PREC, PET…) | **Required, tabular** — the forcing/metzone validation and forcing generator need it; keep as a frame, not graph edges (phase-5 option to add as `external_input` edges) |
| `EXT TARGETS` | Boundary **outputs**: operation member → WDM/DSS | **Defer** — not needed by any current consumer; schema slot reserved (`edge_kind=EXTERNAL_OUTPUT`) |
| `FTABLES` | Reach hydraulics (stage-area-volume-discharge) | **Not connectivity** — consumed separately (FTABLE coverage check U4, lake surface area); expose `ftable_ids` only |
| `SPEC-ACTIONS` | Can conditionally modify state/parameters mid-run | **Out of scope** — can *reference* operations but moves no mass; document as a known non-edge |
| `MON-DATA` | Monthly parameter values | Not connectivity |
| `CATEGORY` | Category tags for CIVOL-style categorized flows | Rare; affects member *subscript semantics*, not topology. Defer; validation can flag block presence |
| `GENER` tables (OPCODE, K) | Define what a GENER *does* to its inputs | **Node attributes**, not edges (reports/gener.py already joins these; builder should expose opcode per GENER node) |
| `FILES` | Binds WDM unit numbers to paths | Needed to *resolve* EXT SOURCES DSNs to files — belongs to the EXT SOURCES frame build, not topology proper |

One subtlety worth coding for: **SCHEMATIC targets missing from OPN
SEQUENCE** (your current `create_graph` comment says "usually the outlet
reach"). These rows must stay in the frames, never silently dropped —
validation detects them as a set difference against `operations`
(finding U1-1 by definition).

---

## Part 2 — Target architecture: modules, types, functions

### 2.0 Design rules (read first — they shape everything below)

Three ownership rules keep this module small and keep other layers' logic
from leaking in:

> **Topology normalizes. Validation judges. The lake persists.**
>
> 1. Topology's only job is to turn UCI blocks into faithful, normalized
>    tables. It never decides whether something is *wrong* — no severities,
>    no diagnostics, no validity flags that require cross-frame checks.
> 2. **Don't store what you can derive.** A column earns storage only if it
>    cannot be recomputed from other columns in the same row or by a cheap
>    set operation against another frame. Row-wise facts (edge role, AFACTR
>    semantics) are helper *functions*; cross-frame facts (dead references,
>    endpoint validity) are the validation layer's set differences.
> 3. **Order and identity bookkeeping belong to whoever persists.**
>    DataFrames preserve row order, and `source_row` already identifies
>    every row. Explicit `connection_order` / `member_order` columns and
>    surrogate keys are added by the lake when it stamps rows to parquet —
>    not here.

Completeness is achieved with one mechanism instead of flags-and-rejects:

> **Nothing is dropped; failures become NA.** Every structurally parseable
> row lands in its frame. A field that fails to normalize (bad TOPLST
> range, uncoercible id) stays NA in an otherwise-kept row. Duplicate OPN
> SEQUENCE rows are both kept. Validation finds problems by scanning for
> NAs, duplicates, and set differences — machinery it already has.

Why this matters: a reach that appears in SCHEMATIC but not OPN SEQUENCE
("dead reach") is precisely validation finding U1-1. Today's `create_graph`
drops it (`.dropna()` on unmapped nodes) — a bug this design removes. Here
the row simply stays in `connections`; validation computes
`endpoints(connections) − keys(operations)` and finds it.

**Prerequisite task this policy exposes:** the parsing layer currently
*filters while parsing*. `expand_extsources` (applied to both `EXT SOURCES`
and `NETWORK` in `document.py`) drops rows whose targets are not simulated
opnids — so dead targets in those two blocks are invisible to everything
downstream today. Phase 2 must add an unfiltered access path (e.g.,
`uci.table(block, filtered=False)` or a raw accessor) and the builder must
use it. SCHEMATIC is not filtered at parse (it is not OPNID-indexed), which
is why its dead rows survive to `create_graph` — the asymmetry itself is
evidence this filtering was never a deliberate policy.

### 2.1 Module layout

```text
src/hspf/model/topology.py        NEW — the single builder (Phase 2)
src/hspf/core/types.py            gains the shared enums (move, not copy)
src/hspf/model/graph.py           slimmed: nx view + traversal (Phase 3)
src/hspf/lake/catalogs/routing.py consumer: run stamping + keys + IO (Phase 4)
src/hspf/lake/catalogs/edges.py   consumer: derived connection catalog (Phase 4)
src/hspf/uci_gis_validations.py   consumer via context adapter (Phase 5)
```

One module, not a package. With HSPF-native columns and no build-time
renaming or pruning, the target size drops to **~200–300 lines**:
source-table gathering ~40, container + views ~60, four builders ~100,
domain helpers ~30, boundary rename maps ~40. If a draft lands far above
that, something from §2.0's "don't store what you can derive" list has
crept back in — or renaming has leaked back into the build. Generic
scalar helpers (`_missing`, `_optional_int`, text cleanup) live in
`hspf/core/utils.py`, shared with the lake's `io.py` — not duplicated here.

### 2.2 Shared types (home: `hspf/core/types.py`)

```python
class RoutingSource(StrEnum):          # moved from lake/catalogs/routing.py
    SCHEMATIC = "schematic"            # the SCHEMATIC × MASS-LINK mechanism
    NETWORK = "network"
    MANUAL = "manual"                  # reserved for lake cross-model rows

class EdgeRole(StrEnum):               # single home; delete the two copies
    LAND_TO_REACH = "LAND_TO_REACH"
    LAND_TO_LAND = "LAND_TO_LAND"
    REACH_TO_REACH = "REACH_TO_REACH"
    UTILITY = "UTILITY"                # GENER/COPY/PLTGEN/etc. involved

class OperationKey(NamedTuple):        # NEW — the node identity everywhere
    operation: str                     # "PERLND" | "IMPLND" | "RCHRES" | ...
    opnid: int
```

Rules:

- `OperationKey` is used **directly as the networkx node key** (tuples are
  hashable). This deletes `G.labels`, `_add_subgraph_labels`,
  `node_labels()`, `get_node_id()` — four lookup mechanisms become zero.
- `edges.py`'s `EdgeKind` is retired in favor of `RoutingSource` (they
  encode the same fact; `routing.py`'s name is the better one). Keep a
  deprecation alias in `edges.py` for one release.
- Existing `OperationType` / `TransformFunction` in core stay as-is; the
  builder coerces *leniently* (unknown → uppercase string), matching the
  relaxed-validation decision already made for `routing.py`.

### 2.3 Frame schemas and build recipes

Four frames, each a near-mechanical image of the UCI block(s) it comes from
— that is the review property: each frame can be checked against the HSPF
manual description of its source block, reinforced by keeping HSPF's own
column names through the build (§2.3.5 defines the boundary renames).
No `run_id` anywhere — run identity is a lake concern added downstream.

General conventions for all recipes:

- **Column names stay HSPF-native through the build.** Frames keep the
  UCI's own names (`SVOL`, `TVOLNO`, `AFACTR`, `MFACTOR`, …) so every
  frame can be eyeballed directly against the UCI file and the HSPF
  manual. Renaming to friendly names happens once, at the consumer
  boundary (§2.3.5) — never during the build.
- **Case signals provenance.** UPPERCASE columns are verbatim UCI fields;
  lowercase columns (`routing_source`, `effective_factor`, `table_name`,
  `filename`, `opn_order`, `in_opn_sequence`, `has_gen_info`,
  `source_row`) are builder-derived.
- **No column pruning at build time.** Merges and concats carry every
  source column along; `member_transfers` is the wide union of both
  mechanisms' columns, with NA holes where a mechanism has no such field.
  Selection happens together with renaming, at the boundary.
- **Range expansion happens at parse time today.** `expand_extsources`
  (applied to `EXT SOURCES` and `NETWORK` in `document.py`) explodes
  `TOPFST`–`TOPLST` ranges and intersects them with simulated opnids —
  matching the FORTRAN semantics in which a range is a *filter*, not an
  assertion. The builder therefore only renames `TOPFST → TVOLNO` and does
  no exploding of its own. The §2.0 caveat stands: this parse-time filter
  also swallows *scalar* dead targets that validation would want to see;
  the unfiltered accessor remains the follow-up task.
- Absent block (e.g., a model with no NETWORK) → empty frame with the
  correct columns, never an error.
- Id fields (`SVOLNO`, `TVOLNO`, `MLNO`, …) are coerced leniently
  (blank → NA); a field that will not coerce becomes NA **in a kept row**
  (§2.0) — there is no reject path and no raise.
- `source_row` (recommended) is the 0-based row index within the parsed
  source block, assigned **before** any merge/concat — the provenance
  receipt that traces every output row to a UCI line. It is the only
  identity/bookkeeping column; order columns are not stored because
  DataFrames preserve row order (§2.0 rule 3).

#### 2.3.1 `operations` — what runs, with its attributes

**UCI inputs:** `OPN SEQUENCE`; `PERLND GEN-INFO`; `IMPLND GEN-INFO`;
`RCHRES GEN-INFO`; `GENER OPCODE`. (No harvesting from other frames — dead
references are found by validation as set differences, §2.0.)

**Recipe:** one row per `OPN SEQUENCE` entry (`opn_order` = 1-based
position), **outer-joined** with the GEN-INFO ids so orphan GEN-INFO rows
remain visible; attach `LSID` / `RCHID`, `LKFG`, `NEXITS`, `OPCODE` by
left join. Duplicated `(OPERATION, OPNID)` entries are kept (validation
flags them).

| Column | Derivation |
| --- | --- |
| `OPERATION`, `OPNID` | the `OperationKey`. The sources name the id differently (`SEGMENT` in OPN SEQUENCE, the index in GEN-INFO) — aligning on `OPNID` is the one in-build rename this frame needs |
| `LSID`, `RCHID` | GEN-INFO name fields, kept separate and HSPF-native (coalescing into one `name` is a boundary rename, §2.3.5); NA when absent |
| `LKFG`, `NEXITS` | RCHRES GEN-INFO; NA for non-reaches |
| `OPCODE` | GENER OPCODE table; NA otherwise |
| `opn_order` | OPN SEQUENCE position; NA for GEN-INFO-only rows |
| `in_opn_sequence`, `has_gen_info` | the two local flags (both sides of the outer join) |

These two flags are kept — unlike everything cut in §2.0 — because they
come from this frame's *own* source tables (no cross-frame computation).

**Dead-reach example:** SCHEMATIC says `RCHRES 7 → RCHRES 8` but 8 is not
in OPN SEQUENCE or GEN-INFO. Then 8 appears nowhere in `operations`, and
the connection row simply remains in `connections`. Validation computes
`endpoints(connections) − keys(operations)` → finds 8 (check U1-1). The
graph view (§2.6) excludes the edge via the same membership test. Nothing
was dropped, nothing was stored to make this detectable.

#### 2.3.2 `connections` — one row per declared connection

**UCI inputs:** `SCHEMATIC`; `NETWORK` (parse-expanded — see the
conventions above and §2.0). **No MASS-LINK join at this grain** — that
happens once, in §2.3.3.

**Recipe, SCHEMATIC side:** the raw SCHEMATIC rows, untouched except for
two derived columns: `routing_source = "schematic"`, `source_row` = row
index. No renames, no join — SCHEMATIC is already at connection grain.

**Recipe, NETWORK side:** take the (parse-expanded) NETWORK frame with
`TOPFST` renamed to `TVOLNO`, then collapse member grain to connection
grain: `groupby(["SVOL", "SVOLNO", "TVOL", "TVOLNO"])`, keeping one row
per group and masking `MFACTOR` to NA wherever the group's values are not
all identical (`nunique(dropna=False) == 1` is the uniformity test).
`routing_source = "network"`; `source_row` = the group's first row index.
Mind that `groupby(...).first()` leaves the keys in the index
(`reset_index()` before concat) and returns the first *non-null* value per
column — acceptable here only because `MFACTOR` is masked separately.

**Combine:** `concat([schematic, network_connections])`. Shared HSPF
column names align automatically; `AFACTR`/`MLNO`/`TMEMSB1/2` are NA on
network rows and `MFACTOR` is NA on schematic rows (its member-grain
values live in §2.3.3).

| Column | Derivation |
| --- | --- |
| `routing_source` | `"schematic"` or `"network"` (`"manual"` reserved for lake cross-model rows) |
| `SVOL`, `SVOLNO`, `TVOL`, `TVOLNO` | verbatim / group key (NETWORK's `TOPFST` arrives renamed to `TVOLNO`) |
| `AFACTR` | SCHEMATIC only; NA on network rows |
| `MFACTOR` | network groups only (uniform value or NA) |
| `MLNO`, `TMEMSB1`, `TMEMSB2` | SCHEMATIC only |
| `source_row` | provenance **and** the link to `member_transfers` |

**Derived, not stored** (one-line helpers/views over this frame):
`edge_role` = `infer_edge_role(SVOL, TVOL)`; `AFACTR` semantics
(area/count/factor) from `SVOL`; `network_area_basis` = network ∧
land→reach; member fan-out count and `unmatched_schematic` by joining
`member_transfers`; endpoint validity by membership against `operations`.

**Join invariant (stated once, tested):** `(routing_source, source_row)`
links `connections` 1-to-N to `member_transfers` for SCHEMATIC rows; for
NETWORK rows the member grain shares the same `source_row` values as the
group it was distinct-ed from.

#### 2.3.3 `member_transfers` — one row per quantity handed off

**UCI inputs:** `SCHEMATIC`; every `MASS-LINK` table; `NETWORK`
(parse-expanded). This is `routing.py`'s existing logic, de-laked — and
the **only join in the module**.

**Recipe, `mass_links` intermediate (recipe book, not transfers):**
concatenate every `MASS-LINK n` table, adding two columns derived from the
table name: `MLNO` (parse the number off the name; strip whitespace;
unparseable → NA, rows kept) and `table_name` (free provenance).
**Normalize `MLNO` dtype to match SCHEMATIC's `MLNO` before joining** — a
string-vs-int (or `"2"` vs `" 2"`) mismatch does not error, it silently
yields zero matches and makes every schematic row look unmatched.

**Recipe, SCHEMATIC × mass_links side:**

1. **Left-join** SCHEMATIC to `mass_links` on `(MLNO, SVOL, TVOL)` with
   suffixes `("_schematic", "_masslink")`. Why these keys: a template row
   applies only when the cited template number matches *and* its declared
   source/target volume types match the SCHEMATIC pair (one template can
   hold rows for several type-pairs). Left join so unmatched SCHEMATIC
   rows survive — they appear as member rows with all member fields NA
   (detectable: `MLNO` present, members NA; no stored flag needed).
2. Resolve the one genuinely colliding field pair: `TMEMSB1/2` =
   SCHEMATIC's value when non-blank, else MASS-LINK's (the override rule,
   §1.2 — the `_prefer` helper over the two suffixed columns).
3. `effective_factor = AFACTR × MFACTOR`, treating blank MFACTOR as 1.0
   (HSPF convention — confirm whether the parser already applies the
   default; fill before multiplying if it does not); `routing_source =
   "schematic"`.

**Recipe, NETWORK side:** each (parse-expanded) NETWORK row *is* a member
transfer; rename `TOPFST → TVOLNO`, set `effective_factor = MFACTOR`,
`routing_source = "network"`. Nothing else.

**Combine:** `concat([schematic × mass_links, network])`. Because both
sides keep HSPF-native names, the shared columns align with no renaming;
the NA holes are the meaningful asymmetries (next table).

| Column | Derivation |
| --- | --- |
| `routing_source`, `SVOL`, `SVOLNO`, `TVOL`, `TVOLNO` | as in §2.3.2 |
| `SGRPN`, `SMEMN`, `SMEMSB1/2`, `TGRPN`, `TMEMN` | MASS-LINK row (schematic side) or NETWORK row inline; all NA on unmatched-recipe rows |
| `TMEMSB1/2` | resolved override (schematic side) or verbatim (network side); the suffixed `_schematic`/`_masslink` intermediates ride along until boundary selection |
| `TRAN` | NETWORK only (neither SCHEMATIC nor MASS-LINK carries it) |
| `AFACTR`, `MFACTOR`, `effective_factor` | §1.4 / §1.5 arithmetic above; `AFACTR`/`MLNO` NA on network rows |
| `MLNO`, `table_name` | schematic side only |
| `source_row` | SCHEMATIC/NETWORK row index — the link back to `connections` |

Not stored (all derivable): `member_order`/`mass_link_row` (frame row
order), `source_block` (from `routing_source`), `edge_role`, endpoint
flags, `unmatched_schematic` (member fields NA). If the lake needs
explicit order columns for stable `transfer_key` hashing, it adds them at
stamping time (§2.0 rule 3).

#### 2.3.4 `external_inputs` — the model's boundary inputs

**UCI inputs:** `EXT SOURCES` (parse-expanded; the parse layer currently
also drops rows targeting non-simulated opnids — the scalar-dead-target
caveat, §2.0); `FILES`.

**Recipe:** the parse layer has already expanded `TOPFST`–`TOPLST`;
rename `TOPFST → TVOLNO` for consistency with the other frames; normalize
`SVOL` in place (uppercase, `"WDM"` → `"WDM1"`, the existing
`build_warehouse` convention); left-join `FILES` on `FTYPE == SVOL` →
`filename` (no match → NA; FILES-path existence is the inventory
enforcer's job, not topology's).

| Column | Derivation |
| --- | --- |
| `SVOL`, `SVOLNO` | volume type (normalized in place) and DSN |
| `filename` | FILES join (lowercase: derived) |
| `SMEMN`, `SSYST` | source member and system, verbatim |
| `TVOL`, `TVOLNO` | target operation and id (`TOPFST` renamed) |
| `TMEMN`, `TGRPN` | target member and group, verbatim |
| `MFACTOR`, `TRAN` | verbatim (blank MFACTOR → 1.0) |
| `source_row` | provenance |

Note this frame is deliberately *wider than PREC*: every met member and
point-source input lands here, so U5/U6/U9 and the forcing generator all
read one frame. `precip_assignments()` (§2.4) is just a filter on it.

Design notes the implementer should not relitigate:

- The AFACTR overload (§1.2) is handled by *helper functions*, not stored
  columns: area aggregations filter on land-source rows (the semantics are
  a pure function of `SVOL`). This fixes the `graph.py`
  area-summing bug structurally without widening the frames.
- Two grains exist on purpose: areas are asked at connection grain (AFACTR
  repeats across member rows — §1.4); quantity semantics at member grain.
- Provenance (`source_row` + `routing_source`) is non-negotiable — it is
  what turns any downstream discrepancy into a one-minute lookup.

#### 2.3.5 Boundary renames — final column selection per table

The build keeps HSPF-native names end-to-end (general conventions above).
Consumers that want stable, self-describing schemas — the lake catalogs,
the validation context adapter, anything persisted — apply **one**
selection + rename at their boundary. The mappings below are the suggested
standard so every consumer that renames agrees. Columns not listed are
dropped at selection (e.g., the suffixed `TMEMSB*_schematic` /
`TMEMSB*_masslink` intermediates and `table_name`).

**`operations`**

| Build column | Final name |
| --- | --- |
| `OPERATION` | `operation` |
| `OPNID` | `opnid` |
| `LSID` / `RCHID` | `name` (coalesced) |
| `LKFG` | `lkfg` |
| `NEXITS` | `nexits` |
| `OPCODE` | `gener_opcode` |
| `opn_order`, `in_opn_sequence`, `has_gen_info` | unchanged |

**`connections`**

| Build column | Final name |
| --- | --- |
| `SVOL`, `SVOLNO` | `source_operation`, `source_id` |
| `TVOL`, `TVOLNO` | `target_operation`, `target_id` |
| `AFACTR` | `afactr` |
| `MFACTOR` | `mfactor` |
| `MLNO` | `mlno` |
| `TMEMSB1`, `TMEMSB2` | `tmemsb1`, `tmemsb2` |
| `routing_source`, `source_row` | unchanged |

**`member_transfers`** — the `connections` mappings plus:

| Build column | Final name |
| --- | --- |
| `SGRPN`, `SMEMN`, `SMEMSB1`, `SMEMSB2` | `source_group`, `source_member`, `source_sub1`, `source_sub2` |
| `TGRPN`, `TMEMN` | `target_group`, `target_member` |
| `TMEMSB1`, `TMEMSB2` (resolved) | `target_sub1`, `target_sub2` |
| `TRAN` | `tran` |
| `effective_factor` | unchanged |

**`external_inputs`**

| Build column | Final name |
| --- | --- |
| `SVOL` | `svol` |
| `SVOLNO` | `dsn` |
| `SMEMN`, `SSYST` | `source_member`, `ssystem` |
| `TVOL`, `TVOLNO` | `target_operation`, `target_id` |
| `TMEMN`, `TGRPN` | `target_member`, `target_group` |
| `MFACTOR`, `TRAN` | `mfactor`, `tran` |
| `filename`, `source_row` | unchanged |

Where this runs: in the lake stamping functions (§2.7) and the validation
context adapter (§2.8). If several consumers want the renamed form, add a
single optional helper (e.g., `rename_topology_frames(topology)`) rather
than letting each consumer's rename map drift.

### 2.4 The container dataclass

```python
@dataclass(frozen=True)
class ModelTopology:
    operations: pd.DataFrame           # HSPF-native columns (§2.3.1)
    connections: pd.DataFrame          # HSPF-native columns (§2.3.2)
    member_transfers: pd.DataFrame     # HSPF-native columns (§2.3.3)
    external_inputs: pd.DataFrame      # HSPF-native columns (§2.3.4)
    ftable_ids: frozenset[int]         # parsed from FTABLE{n} table names

    # Small derived views (computed on call, never stored):
    #   operation_keys()       -> set[OperationKey] from operations
    #   runnable_connections() -> rows whose endpoints are both in
    #                             operation_keys() (membership computed here)
    #   reach_edges()          -> runnable, both ends RCHRES
    #   land_to_reach()        -> runnable, infer_edge_role == LAND_TO_REACH
    #   precip_assignments()   -> external_inputs[TMEMN == "PREC"]
```

**There is no `diagnostics()` method and no `rejected_rows` frame.**
Topology's whole obligation to quality is *don't hide anything* — satisfied
by the NA rule (§2.0). The judgments live in `uci_gis_validations.py`,
which already owns these exact checks and their severities/waivers:

| Validation finds it by | Check |
| --- | --- |
| `endpoints(connections) − operation_keys()` | dead/phantom references (U1-1, U1-2) |
| `operations` rows with `in_opn_sequence ∧ ¬has_gen_info` (or reverse) | GEN-INFO reconciliation (U1-4) |
| `member_transfers` rows with `MLNO` present but member fields NA | unmatched MASS-LINK (U1-5) |
| `external_inputs` targets not in `operation_keys()` | dead EXT SOURCES targets (U1-3) |
| NA `TVOLNO` / duplicated operation keys | malformed ranges, duplicate OPN SEQUENCE rows |
| unhandled blocks (CATEGORY, SPEC-ACTIONS…) | validation reads `uci.block_names()` directly |

Frozen + pure-derived + rebuilt-on-demand: the three properties that keep a
parallel representation honest (per the consolidation plan §2).

### 2.5 Builder functions (extraction map from `routing.py`)

```python
def build_topology(uci) -> ModelTopology            # gathers tables, delegates
def build_topology_from_tables(tables) -> ModelTopology
```

`build_topology` is the only function that touches the UCI object: it
declares the direct source tables up front (the `TopologySourceTables`
bundle) and hands them to `build_topology_from_tables`. **The build is
linear and each frame is independent** — no frame needs another frame as
input, so there is no backfill pass and no circular ordering:

```text
operations        ← OPN SEQUENCE + GEN-INFOs + GENER OPCODE
connections       ← SCHEMATIC + NETWORK
member_transfers  ← SCHEMATIC × MASS-LINK  ∪  NETWORK
external_inputs   ← EXT SOURCES + FILES
```

Style rule that keeps the builders small: **vectorized
`rename`/`assign`/`merge`, not row loops.** Building rows as dict literals
via `iterrows` is 3–4× the lines and is how the first draft ballooned.
Each builder should read like its §2.3 recipe.

Implementation gotchas (each has bitten a draft):

- **Copy before mutating.** `uci.table(...)` may hand back a frame shared
  with the parser's internal state; `inplace=True` renames or column
  assignments on it corrupt every later reader of that block. First
  statement of every builder: `.copy()`.
- **Join-key dtypes.** `MLNO` parsed off a table name is a string;
  SCHEMATIC's `MLNO` may be int or padded text. Cast both sides to one
  dtype (and strip whitespace) before the merge — a mismatch produces
  zero matches, not an error.
- **`groupby(...).first()`** returns the first *non-null* value per column
  (not the first row) and leaves the group keys in the index. Mask
  `MFACTOR` uniformity separately; `reset_index()` before concat.
- **Missing blocks.** Guard `SCHEMATIC`, `NETWORK`, `MASS-LINK`, `GENER`,
  `FTABLES` with `block_names()` / `table_names()` checks; `pd.concat` of
  an empty list raises, so the mass_links loop needs an empty-frame
  fallback.

| New function | Extracted from | Changes during extraction |
|---|---|---|
| `_operations_frame(...)` | `graph.py` node loop + GEN-INFO loops | outer join of OPN SEQUENCE and GEN-INFO ids; no mention harvesting; HSPF-native columns |
| `_mass_links_frame(...)` | `routing.py` same name | concat + `MLNO`/`table_name` derived from table name (strip; unparseable → NA, rows kept); normalize `MLNO` dtype to SCHEMATIC's |
| `_schematic_mass_link_frame(...)` | `routing.py` same name | left join on `(MLNO, SVOL, TVOL)`, suffixes `("_schematic", "_masslink")`; `_prefer` resolves `TMEMSB1/2`; no renames |
| `_network_transfers_frame(...)` | `routing.py` same name | parse-expanded input; `TOPFST → TVOLNO` rename; `effective_factor = MFACTOR` |
| `_member_transfers_frame(...)` | `routing.py` record loop | plain `concat` of the two sides — shared HSPF names align without mapping; no run_id, no transfer_key, no order columns |
| `_connections_frame(...)` | NEW, small | raw SCHEMATIC + NETWORK groupby with the MFACTOR-uniformity mask; no join-derived columns |
| `_external_inputs_frame(...)` | `views.py` `get_dsns` / `infer_metzones` logic | generalized to all members; SVOL normalize + FILES join |
| `infer_edge_role(...)` | `routing.py` same name | stays a function; its output is never stored |

Generic scalar helpers (`_missing`, `_optional_int`, blank-to-NA, text
cleanup) move to `hspf/core/utils.py` and are shared with the lake's
`io.py` rather than duplicated a third time. Topology keeps only domain
helpers: `infer_edge_role`, `_mass_link_number`, the AFACTR-semantics
function.

Explicit non-goals for the builder (defer, with schema slots reserved):
EXT TARGETS frame; graph edges for external inputs; CATEGORY expansion;
SPEC-ACTIONS. Detecting their *presence* is a validation check against
`uci.block_names()`, not a topology feature.

### 2.6 Graph view (`graph.py` after Phase 3)

```python
def create_graph(topology: ModelTopology, *,
                 include_land: bool = True) -> nx.MultiDiGraph
```

- Nodes: `OperationKey` tuples; attributes from `operations` frame.
  Node set = `in_opn_sequence == True`; edges come from
  `runnable_connections()` (endpoint membership computed in the view).
  Dead/phantom operations never enter the graph — they stay visible in
  the frames, where validation finds them.
- Edges: **connections grain only** (one edge per connection row), attrs =
  the connection row fields. Member transfers do NOT become edges (the
  overcount hazard, §1.4); they remain reachable via the topology object.
- `area` edge attribute set **only for land-source rows** (the
  AFACTR-semantics helper) — existing `watershed_area`/`catchment_area`
  summation becomes correct without changing those functions.
- `reachNetwork` facade: constructor becomes
  `build_topology(uci)` → `create_graph(topology)`; all 12 public methods
  keep signatures. `uci.network` becomes a lazy `functools.cached_property`.
- Delete: `Node` class, labels machinery, `to_dataframe` mutation bug
  (build row dicts instead of writing into `edge_data`), dead commented
  blocks, module-level `subwatersheds()` circular dependency (reimplement
  on `topology.land_to_reach()`).

### 2.7 Lake consumers (Phase 4)

`routing.py` keeps its public API; internals become:

```python
def routing_transfers_from_uci(uci, run_id):
    topology = build_topology(uci)
    frame = topology.member_transfers.copy()
    frame["run_id"] = run_id
    # Lake-owned bookkeeping added at stamping time (§2.0 rule 3):
    # order columns for deterministic hashing, then transfer_key.
    frame["member_order"] = _order_within_connection(frame)
    frame["transfer_key"] = _make_transfer_keys(frame)
    return _coerce_routing_transfers_frame(frame)
```

`edges.py` loses `edges_from_uci`-style extraction; gains:

```python
def edges_from_topology(topology, run_id, *, target_run_id=None) -> pd.DataFrame
    # topology.connections + run_id stamp; target_run_id reserved for
    # cross-model rows injected from the inventory linkage registry
```

Cross-model routing (the packaging question): implemented **only** here —
a lake-side function reads `linkages/linkages.yaml` (model inventory) and
appends `MANUAL`-source edge rows with `target_run_id` set. pyhspf never
learns about other models; the one-way dependency survives the package
split.

### 2.8 Validation + future consumers (Phase 5)

The `UciGisValidationContext` adapter becomes mechanical:

| Context method | Topology source |
|---|---|
| `opn_sequence()` | `operations` (rename columns) |
| `rchres_edges()` | `topology.reach_edges()` |
| `routing_edges()` / `land_to_reach_edges()` | `connections` filtered |
| `schematic/network_member_transfers()` | `member_transfers` by `routing_source` |
| `ext_sources()` / precip assignments | `external_inputs` |
| `ftable_ids()` / `geninfo_ids()` | `ftable_ids` / `operations` |

Forcing generator (future): consumes `precip_assignments()` + the committed
metzone↔DSN crosswalk — no new extraction. U3 reach classification:
computed from `connections` plus the helper functions (`infer_edge_role`,
AFACTR semantics, NETWORK-area detection), resolving today's three
competing "routing reach" definitions.

---

## Part 3 — Test plan (the actual safety mechanism)

1. **Baseline capture (Phase 0):** per model × 68: edge list from old
   `create_graph`, `subwatersheds()`, `outlets()`, `drainage_area()` per
   outlet; serialized to parquet under the golden suite.
2. **Reconciliation invariants (Phase 2, the core):** for each model assert
   - `operations` keys == OPN SEQUENCE ∪ GEN-INFO id sets (exact);
   - land area per reach from `connections` (land-source rows only)
     == direct `SCHEMATIC` groupby sum (exact, no tolerance);
   - member grain re-aggregated on `(routing_source, source_row)` matches
     `connections` 1-to-N losslessly;
   - every `connections` row traces to a real `source_row`;
   - SCHEMATIC-only subset of new edges == Phase 0 edge list, with the
     diff report empty or itemized as NETWORK rows / rows the old code
     silently dropped (now present in the frames and detected by
     validation as set differences).
3. **Differential tests (Phase 3/4):** old vs new `reachNetwork` answers
   (allowed diffs: NETWORK models, documented); lake catalog before/after
   byte-comparison (expected diff: **zero** — routing.py already handled
   both blocks, so this is the strongest single check that extraction
   preserved behavior).
4. **Unit fixtures:** hand-written minimal UCIs covering: unmatched MLNO,
   TMEMSB override, NETWORK range explode, NETWORK+SCHEMATIC overlap,
   GENER count semantics, missing-target outlet reach, COPY met fan-out.

Suggested order of work: Phase 0 → 1 → 2 (with §3.2 passing on all 68)
→ 3 → 4 → 5, per the consolidation plan. Phase 2 is the only phase with
real design risk, and this spec pins its decisions; everything after is
rewiring under test coverage.

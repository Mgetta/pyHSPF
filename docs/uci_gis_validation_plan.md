# UCI ↔ GIS Validation Plan

**Status:** Implementation-ready plan
**Date:** 2026-09-30
**Scope:** Minimum validation set to establish trust between a UCI file and its
spatial vector layers (reach layer + catchment layer), sufficient to begin
correcting the GIS layers and, ultimately, to generate meteorological forcing
inputs from the catchment layer.

---

## 1. Purpose and framing

### The campaign goal

The catchment GIS layer should become the source that meteorological forcing
inputs are generated from. Today there is no enforced consistency between the
UCI and the GIS layers, so the first step is a bounded validation campaign:
run the checks below, triage every finding into *fix the GIS*, *fix the UCI*,
or *intentional (waive with a reason)*, and drive the diff to zero.

The north-star check that everything else supports:

> **The metzone round-trip (G5):** group operations by their PREC DSN (from
> EXT SOURCES), independently derive each operation's spatial metzone from
> the catchment layer, and diff the two. Every difference is exactly one of:
> a GIS error, a UCI error, or an intentional decision. That diff *is* the
> GIS-update work list.

Every other check earns its place by one criterion: **it makes some quantity
in that diff (or the reach-set/topology diffs) well-defined.** A UCI-internal
check is in scope only if, without it, a Stage-2 comparison would be
ambiguous or noisy. This is deliberately a *minimum* set — it flags likely
modeler errors and blocking inconsistencies, not a full UCI standard.

### The metzone circularity (important)

Metzone membership is currently *inferred from* the PREC DSN in EXT SOURCES —
there is no independent record of which operation belongs to which metzone,
only faith that the original modeler was consistent. This means a naive check
("does the operation's metzone match its PREC DSN?") is circular and passes
by construction.

The catchment layer is the only independent source of spatial truth, so G5 is
structured as a comparison between **two independent derivations**:

1. **UCI side — DSN-groups:** operations grouped by shared PREC DSN. No
   spatial meaning claimed; just "who shares a rain gage."
2. **GIS side — spatial metzones:** each operation's metzone derived from the
   catchment polygons it is spatially associated with (reaches directly;
   land operations via the routing block).

The check reports *incoherence between the two derivations*, which works even
though neither side is trusted yet. Once the campaign drives the diff to
zero, the GIS layer graduates into the official source of truth for metzone
membership — the precondition for generating forcing from it.

### Design principles

1. **Checks emit findings, never verdicts.** Every finding carries a stable
   check id, a severity, a subject, and expected-vs-actual values.
   Intentional quirks are handled later by waivers keyed to (check id,
   subject) — the only obligation now is stable ids for waivers to attach to.
2. **Stages gate at the subject level, not the model level.** One reach
   missing from the GIS layer must not generate forty downstream findings —
   and must not block validating the other 200 reaches. A subject that fails
   Stage 0/1 is excluded from Stage 2 and reported as excluded.
3. **Classification is output, not judgment.** Lakes, routing-only reaches,
   terminal dummy lakes, non-contributing areas are a derived *reach
   classification table* that Stage 2 consumes to decide which checks apply
   to which reach. This converts most "intentional weirdness" from false
   positives into data.
4. **Truth direction is decided per finding, not per check.** For reach sets
   and topology the UCI is provisional truth (this campaign edits GIS). For
   metzone assignment the GIS is closer to physical truth (a "spatially
   impossible" PREC DSN is a UCI error found *via* GIS). Checks report
   symmetric disagreements; triage decides the edit direction.
5. **Routing truth is the union of SCHEMATIC and NETWORK.** NETWORK is a
   full alternative to SCHEMATIC (direct member-to-member transfers with a
   single MFACTOR, no AFACTR, no MASS-LINK), and models may carry either or
   both. Any check that consumes connectivity must consume the union, or it
   is wrong on some subset of the 68 models (false terminals, false
   disconnections, false routing-only classifications).

### Severity vocabulary

| Severity | Meaning |
| --- | --- |
| `error` | Comparison-blocking or physically impossible; must be fixed or explicitly waived before the model's GIS layers can be trusted |
| `warning` | Suspicious; requires human triage (fix or waive) |
| `info` | A classification fact or legitimate-pattern note; recorded for visibility, no action required |

---

## 2. The complete check table

### Stage 0 — GIS-internal

Run first. Without these, "the GIS says X" is not a meaningful statement.

| ID | Name | What is checked | Why / what it enables | Severity |
| --- | --- | --- | --- | --- |
| G0-1 | Reach key validity | `ReachID` in the reach layer is non-null and unique | Every Stage-2 join is keyed on `ReachID`; duplicates make every downstream comparison ambiguous | error |
| G0-2 | Downstream reference validity | Every `DS_ReachID` resolves to an existing `ReachID` or an outlet sentinel (999/-999); no reach lists itself as its own downstream | Makes "the GIS's downstream relationship" well-defined for G2 | error |
| G0-3 | Reach graph sanity | The GIS reach network contains no cycles; the number of outlets is counted and reported | A cyclic GIS network can't be compared to the UCI network; outlet count is context for G2 terminal checks | error (cycles) / info (outlet count) |
| G0-4 | Catchment attribute completeness | Every catchment polygon has a non-null reach assignment and a non-null metzone label | G4 and G5 are undefined for polygons missing either attribute | error |

### Stage 1 — UCI-internal

Minimum internal coherence so the UCI can serve as one side of Stage-2
comparisons. Canonical operation set = **OPN SEQUENCE** (what actually runs);
all other blocks must reconcile to it.

| ID | Name | What is checked | Why / what it enables | Severity |
| --- | --- | --- | --- | --- |
| U1-1 | SCHEMATIC membership | Every SCHEMATIC `SVOLNO`/`TVOLNO` exists in OPN SEQUENCE for its operation type | Reaches/land segments in the schematic that never run are dangling references (an observed real-world inconsistency); makes "the UCI's operation sets" well-defined | error |
| U1-2 | NETWORK membership | Every NETWORK `SVOLNO`/`TVOLNO` — with target ranges expanded — exists in OPN SEQUENCE | Same referential integrity as U1-1 for NETWORK-using models; range expansion catches ranges silently spanning nonexistent opnids | error |
| U1-3 | EXT SOURCES target membership | Every EXT SOURCES target — with `TOPFST`–`TOPLST` ranges expanded — exists in OPN SEQUENCE | Forcing assigned to operations that never run is dead weight or a typo for a real target; expansion catches hidden range errors | error |
| U1-4 | GEN-INFO reconciliation | Every OPN SEQUENCE operation has its GEN-INFO row; GEN-INFO rows without an OPN SEQUENCE entry are orphans | Missing GEN-INFO breaks classification (U3 needs LKFG); orphan tables are clutter, not breakage | error (missing) / warning (orphan) |
| U1-5 | MASS-LINK references | Every `MLNO` referenced by SCHEMATIC has a MASS-LINK definition | A schematic row pointing at a missing mass-link is a broken transfer | error |
| U1-6 | Dangling land segments | PERLNDs/IMPLNDs in OPN SEQUENCE that appear as a source in neither SCHEMATIC nor NETWORK | Land that runs but drains nowhere — sometimes intentional non-contributing land, often an omission | warning |
| U2-1 | Routing graph acyclicity | The RCHRES→RCHRES graph built from the **union** of SCHEMATIC and NETWORK edges contains no cycles | A cyclic routing network is a hard modeling error and makes "UCI downstream" (G2) undefined | error |
| U2-2 | Outlet count | Number of outlets in the union routing graph, reported | Context for G2 terminal checks; some models legitimately have several outlets | info |
| U2-3 | Disconnected sub-networks | Sub-networks of the union graph not connected to any outlet-bearing network | Sometimes intentional (separately modeled areas); often a broken connection | info |
| U3 | Reach classification | Derived table, one row per reach: `lake` (LKFG=1), `routing-only` (no incoming area), `terminal`, `non-contributing` (in schematic, absent from routing graph), `dummy-terminal-lake` (terminal + lake + no meaningful routing), `network-area-basis` (receives land contributions only via NETWORK, where area is folded invisibly into MFACTOR) | Not pass/fail — the classification table is a first-class output that G2/G4 (and a future G6) consume to decide which checks apply to which reach; converts special cases from false positives into data | info (each classification emitted for visibility) |
| U4-1 | FTABLE coverage | Every routed RCHRES has `FTABLE{id}`; exception: reaches classified `dummy-terminal-lake` | A routed reach without an FTABLE cannot simulate; dummy terminal lakes legitimately omit it | error / info (exception) |
| U4-2 | Orphan FTABLEs | FTABLEs with no corresponding RCHRES in OPN SEQUENCE | Clutter or a renumbering leftover; harmless but worth surfacing | info |
| U5-1 | Land forcing completeness | Every PERLND/IMPLND receives at minimum PREC and PET via EXT SOURCES | PWATER/IWATER cannot run without them; a missing assignment is a hard error before any run | error |
| U5-2 | Lake forcing completeness | Every LKFG=1 RCHRES receives PREC and PEVT | Lake surfaces receive precip/evap directly on the RCHRES; missing is suspicious but occasionally deliberate | warning |
| U6-1 | Duplicate PREC targets | Multiple EXT SOURCES PREC rows to the same target: MFACTORs summing ≈ 1.0 is legitimate gage weighting; anything else double-counts rainfall | Double precip is one of the worst silent bugs HSPF permits; also, G5 needs "the operation's PREC DSN" to be a well-defined single value (or declared weight set) | info (weights ≈ 1) / error (otherwise) |
| U6-2 | PREC MFACTOR sanity | PREC MFACTORs ≤ 0 or far outside the weight pattern | Catches sign/typo errors that distort forcing invisibly | warning |
| U7 | Subwatershed DSN coherence | Each reach's PREC DSN appears among the PREC DSNs of its direct contributors | UCI-only shadow of G5: pre-localizes suspects without needing a trusted GIS layer. Downgradeable/retirable once G5 runs routinely; legitimate cross-zone cases exist | warning |
| U8 | SCHEMATIC/NETWORK overlap | When both blocks exist: the same source-operation → target-operation transfer with overlapping members defined in both | Double-counted flow — the routing analog of double precip. Factors that complement each other suggest an intentional split; a plain duplicate is an error | warning (looks intentional) / error (plain duplicate) |
| U9 | Assumption guard: no COPY met distribution | No EXT SOURCES PREC (or other met member) rows target COPY operations | The validator resolves "the operation's PREC DSN" as a direct EXT SOURCES lookup. Models that fan met data out through COPY + NETWORK/SCHEMATIC violate that assumption; this guard makes the assumption self-checking so such a model fails loudly instead of validating wrongly | error ("unsupported pattern — requires one-hop DSN tracing") |

### Stage 2 — UCI ↔ GIS

Runs only on subjects that survived Stage 0 and Stage 1 (subject-level
gating). Uses the U3 classification table and the union routing graph.

| ID | Name | What is checked | Why / what it enables | Severity |
| --- | --- | --- | --- | --- |
| G1-1 | Reaches missing from GIS | UCI RCHRES opnids absent from the reach layer | Blocks everything downstream for those reaches — forcing generation, topology, coverage. Top of the GIS-update work list | error |
| G1-2 | Extra GIS reaches | Reach-layer `ReachID`s absent from the UCI | Often intentional (unmodeled reaches, neighboring model's features) — classify, don't delete blindly | warning |
| G2-1 | Topology edge diff | Per reach: the GIS edge `(ReachID, DS_ReachID)` is a member of the UCI's downstream set from the **union** routing graph. Compare as edge *sets*, report the symmetric difference | The core structural agreement between map and model; replaces per-reach upstream/downstream loops with one complete, localized diff | error |
| G2-2 | Multi-exit surplus | UCI downstream edges beyond the single GIS `DS_ReachID` (multi-exit reaches, diversions) | GIS carries one downstream id; extra UCI exits are usually legitimate (diversions) but must be visible | info |
| G2-3 | Terminal concordance | UCI outlets correspond to GIS sentinel values and vice versa | A false terminal on either side is a broken connection | error |
| G3 | Lake concordance | LKFG=1 reaches ↔ GIS lake attribute (where the layer carries one) | Lakes get special handling in coverage and (future) area checks; disagreement means one side mislabels the waterbody | warning |
| G4-1 | Catchment coverage | Every reach classified area-receiving (U3) has ≥ 1 catchment polygon | Without a catchment, that reach's forcing weights cannot be generated from GIS | error |
| G4-2 | Catchment reach validity | Every catchment polygon's reach assignment resolves to a UCI reach | An orphaned catchment either belongs to a missing reach (see G1-1) or carries a typo | error |
| G4-3 | Catchments on routing-only reaches | Catchment polygons assigned to reaches classified routing-only | Either the classification is wrong (model missing area) or the GIS assignment is wrong | warning |
| G5-1 | DSN-group construction | Group all operations by PREC DSN from EXT SOURCES (artifact, not pass/fail) | One side of the round-trip; also the raw material for the committed crosswalk | — (artifact) |
| G5-2 | Spatial metzone derivation | Per operation, derive spatial metzone from the catchment layer: reaches from their own catchments' metzone labels (area-majority); PERLNDs/IMPLNDs from the metzones of the catchments they drain into via the union routing graph | The independent, non-circular side of the round-trip — metzone membership derived from *location*, not from the DSN being validated | — (artifact) |
| G5-3 | Round-trip coherence | Diff G5-1 against G5-2: (a) an operation whose spatial metzone conflicts with the rest of its DSN-group → "spatially impossible precip," a UCI error found via GIS; (b) a GIS metzone label inconsistent with an otherwise-coherent DSN-group → a GIS attribute error | **The campaign centerpiece.** Works even though neither side is trusted yet, because it reports incoherence between independent derivations. Each finding is triaged: fix UCI / fix GIS / waive | warning (each mismatch, triaged individually) |
| G5-4 | Crosswalk conformance | Once a confirmed metzone↔DSN crosswalk is committed (see §4): both the UCI DSN-groups and the GIS metzone labels are checked against it | Prevents silent re-baselining: without a committed table, re-derivation happily infers a *new wrong* grouping after someone edits EXT SOURCES, and confirms it against itself | error (drift from committed crosswalk) |
| G6 | Area comparison | **Deferred by decision.** Direct-drainage-grain comparison of Σ AFACTR vs catchment polygon areas | Deferred until the lake-surface convention is decided (is the lake surface inside the catchment polygon but absent from AFACTR because its precip arrives via RCHRES PREC?). What is lost meanwhile: the only check that catches a catchment assigned to the *right* reach with the *wrong magnitude* (AFACTR typos, stale acreages). G4 still catches existence problems | — (deferred) |

---

## 3. Execution order and gating

```text
Stage 0 (GIS-internal)          G0-1 .. G0-4
        │  subjects failing key checks are excluded and reported
        ▼
Stage 1 (UCI-internal)          U1 .. U9  →  produces reach classification (U3)
        │  subjects failing membership/graph checks are excluded and reported
        ▼
Stage 2 (UCI ↔ GIS)             G1 → G2 → G3 → G4 → G5
```

Triage order for the GIS-update campaign (highest leverage first):

1. **G1-1** missing reaches — blocks everything for those reaches.
2. **G2** topology diffs — the map must route like the model.
3. **G4** coverage — every area-receiving reach needs its catchments.
4. **G5-3** metzone mismatches — the forcing-generation blocker.
5. (**G6** areas — when un-deferred.)

---

## 4. Derived artifacts

Running the validator produces three artifacts per model, not just pass/fail:

1. **Findings table** — one row per finding:
   `check_id, severity, subject_type, subject_id, expected, actual, message`.
   Stable `check_id` + `subject_id` is what future waivers attach to.
2. **Reach classification table** (from U3) — consumed by Stage 2, and useful
   on its own as model documentation.
3. **Metzone ↔ DSN crosswalk** (from G5-1/G5-2) — a handful of rows per
   model: `metzone_label → prec_dsn`. Workflow: **derive → confirm by eye →
   commit** as a small per-model artifact. After that, G5-4 checks against
   the committed table instead of re-deriving fresh each run. Constraints on
   the mapping itself: it must be a *function* (each metzone → exactly one
   PREC DSN); the reverse may legitimately be many-to-one (two metzones
   sharing one gage is valid and the table records it). This table is also
   literally the input the forcing generator needs — validating it *is* a
   dry run of forcing generation.

When the G5 diff reaches zero (every finding fixed or waived), the GIS layer
graduates into the official source of truth for metzone membership.

---

## 5. Preconditions and open items

| Item | Status |
| --- | --- |
| Metzone membership source | Currently inferred from PREC DSNs (no independent record); G5 is structured around this — the GIS layer becomes the independent side, then the source of truth |
| COPY met-distribution survey | Assumed absent; U9 makes the assumption self-checking. If any model fans met through COPY, DSN resolution needs a one-hop trace through NETWORK/SCHEMATIC for that model |
| Lake-surface area convention | Undecided; blocks G6 (deferred with it) |
| Area checks (G6) | Deferred by decision; revisit after the lake convention is settled |
| Outlet sentinel values | Plan assumes 999/-999 in `DS_ReachID`; confirm this is uniform across all 68 models' layers |
| Waiver mechanism | Not needed for round one — but check ids and subject ids are stable from day one so waivers can attach later |

Explicitly out of scope for this campaign: parameter-value standards,
activity-flag conventions, unit-system flags, EXT TARGETS/output conventions,
WDM-side checks (DSN existence and period-of-record coverage — a separate
UCI↔WDM campaign), PERLND landcover composition vs landcover rasters, point
source spatial checks.

---

## 6. Mapping from the existing validations.py

Reference for implementation — where each function in
[`src/hspf/validations.py`](../src/hspf/validations.py) lands in this plan:

| Existing function | Fate |
| --- | --- |
| `duplicates`, `is_duplicate`, `is_missing` | → G0-1, G1 |
| `gis_only`, `missing` | → G1-2, G1-1 (the two directions, distinct severities) |
| `test_upstream` / `test_downstream` | → merged into G2-1's single edge-set diff (comparing edge sets once catches everything both directions caught, with one localized report) |
| `similar_area` | → G6 (deferred); when revived: lake quarantine, direct-drainage grain, and the m²→acres constant surfaced in one visible place |
| `same_metzone` (defined twice; the second silently shadows the first) | → G5; the shadowing bug is itself an argument for stable check ids |
| `same_dsns` | → U7 |
| `has_ftable` | → U4-1 |
| `isin_open_sequence`, `isin_geninfo`, `isin_schematic`, `svol_isin_schematic`, `tvol_isin_schematic` | → U1's set-vs-set reconciliations (one pass over whole sets, not per-id membership calls) |
| `is_lake`, `is_routing_reach`, `is_non_contributing_area`, `has_area`, `number_of_networks` | → U3 classification table + U2-2 |
| `gets_precip` | currently tests network membership, which is a different question — replaced by U5's actual EXT SOURCES test |
| Buffalo dummy-terminal-lake note | → U3 `dummy-terminal-lake` class + U4-1 exception |

Implementation notes carried from the discussion:

- Prefer set-level comparisons over per-subject boolean loops: the campaign
  question is "what is the complete diff?", and set operations produce the
  full work list in one pass.
- The finding/report structures in `src/hspf/lake/validate.py`
  (`ValidationIssue` / `ValidationCheckResult` / `ValidationReport`) are
  domain-neutral and can be reused rather than reinvented.
- Build the routing graph once (union of SCHEMATIC and NETWORK, with
  NETWORK target ranges expanded) and feed it to U2, U3, G2, G4, and G5-2 —
  it is the single shared data structure of the whole validator.

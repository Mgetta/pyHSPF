# Consolidating Model Connectivity: Implementation Plan

**Status:** Proposed plan
**Date:** 2026-09-30
**Audience:** Written for review by non-programmers; technical footnotes are
kept to a minimum and every step explains *what* will be done and *why*.

---

## 1. The problem in plain terms

Every HSPF watershed model is, at its heart, a set of **connections**: which
land areas drain into which stream segments, which stream segments flow into
which downstream segments, and what quantities (water, sediment, nutrients)
are handed off along each connection. Almost everything we do with a model —
reports, maps, quality checks, the results warehouse — depends on knowing
these connections correctly.

Today, the answer to "what are this model's connections?" is computed in
**three different places in our code, three different ways**:

| Code location | What it computes | Used by | Completeness |
| --- | --- | --- | --- |
| `graph.py` (oldest) | A network of model connections | All reporting (load summaries, drainage areas, upstream/downstream lookups) | **Incomplete** — reads only one of the two blocks of the model file where connections can be declared, and silently discards connections it cannot resolve |
| `routing.py` (newest) | A detailed table of every quantity handed off along every connection | The results warehouse (the "lake") | Most complete — handles both declaration blocks and the hand-off recipes |
| `edges.py` | A summary table of connections for the warehouse | The results warehouse | Partial scaffold, overlaps with both of the above |

This is a problem for three reasons:

1. **The three copies can disagree.** They already do: the oldest copy misses
   an entire category of connections (the NETWORK block), so any model using
   that feature gets silently wrong drainage areas and upstream/downstream
   answers from our reports, while the warehouse sees the model correctly.
2. **Every fix must be made three times.** Each copy has its own bugs and its
   own blind spots; fixing one does nothing for the others.
3. **Planned work multiplies the problem.** The model-vs-GIS validation
   campaign and the meteorological forcing generator both need connection
   information. Without consolidation, each would become a *fourth and fifth*
   copy.

The plan below merges the three implementations into **one** — a single,
well-tested "connection builder" — and turns the other two locations into
thin consumers of it. When it is done, there will be exactly one piece of
code that answers "what are this model's connections?", and every report,
check, and warehouse table will get the same answer.

---

## 2. The design principle: who should own what

The guiding rule is **scope of knowledge**:

> Facts about **one model file** belong in the core `pyhspf` package.
> Facts about **many models, runs, or how models relate to each other**
> belong in the warehouse (lake) layer.

Applied to connections:

| Fact | Example | Owner |
| --- | --- | --- |
| "Land segment 101 drains to reach 5 with 42.7 acres" | Declared inside one UCI file | **pyhspf** (core package) |
| "This connection existed in run `sauk_r03_2026_09` of the model" | Ties a connection to a specific archived run | **Lake** (warehouse layer) |
| "Reach 30 of the Sauk model feeds the Osakis model" | No single model file declares this; it is a fact about the *fleet* of models | **Lake / model inventory** — never pyhspf |

This directly answers the packaging question raised during planning:

- **Yes, the connection-building work belongs in `pyhspf`** — it is purely a
  function of one UCI file, which is exactly what `pyhspf` parses.
- **Yes, the lake can still move to a separate package later.** The lake will
  *depend on* pyhspf (one direction only) and add its own concerns on top:
  run identity, permanent storage, and cross-model connections.
- **Cross-model routing is not "out of place" anywhere** once the rule above
  is adopted: it was never a single-model fact, so it never belonged in
  pyhspf. It lives at the lake/inventory level, where the model-linkage
  registry (see the model inventory proposal, `linkages/linkages.yaml`)
  already provides its authoritative source. The lake's edge table simply
  carries an optional "this connection crosses into another model/run" field
  — which the `edges.py` scaffold already anticipated (`target_run_id`).

### The target architecture

```text
                     ONE UCI FILE (the only source of truth)
                                    │
                                    ▼
              ┌────────────────────────────────────────────┐
              │   pyhspf: "topology builder" (NEW, single   │
              │   implementation of connection extraction)  │
              │   Produces plain tables:                     │
              │   • operations (the model's building blocks) │
              │   • connections (who connects to whom, from  │
              │     BOTH declaration blocks, with receipts)  │
              │   • member transfers (what is handed off)    │
              │   • diagnostics (rows that could not be      │
              │     resolved — reported, never discarded)    │
              └────────────────────────────────────────────┘
                     │                │                 │
         ┌───────────┘                │                 └───────────┐
         ▼                            ▼                             ▼
  pyhspf: graph.py             pyhspf: validation            Lake: routing.py
  (traversal view for          checks (UCI↔GIS               and edges.py
  reports: upstream,           campaign consumes             (add run identity,
  downstream, drainage         the same tables)              permanent keys,
  areas — unchanged                                          storage, and
  interface for reports)                                     cross-model links)
```

Three properties make this safe against the "wrong parallel copy" risk:

1. **Pure derivation.** The tables are rebuilt from the model file on demand
   by one deterministic function. Nothing is hand-edited or patched in place,
   so the tables cannot drift from the file.
2. **Receipts on every row.** Every connection records which block and which
   line of the model file it came from, so any number can be traced back.
3. **Reconciliation tests.** For all 68 models, automated tests assert that
   totals computed from the new tables equal totals computed directly from
   the raw model file (for example: total drainage area per reach). A derived
   copy that is continuously reconciled against its source on 68 real models
   cannot silently lie.

---

## 3. What happens to each of the three modules

**`graph.py` (core package) — slimmed into a "view."**
Keeps its job (answering upstream/downstream/drainage questions for reports)
and its public interface, so the nine reporting modules that use it do not
change. Loses its private, incomplete connection-extraction logic — it will
build its network from the shared topology tables instead. Along the way we
fix known defects: roughly a third of the file is dead code to delete; it
silently discards unresolvable connections (they become visible diagnostics
instead); one function accidentally modifies the data it reads; and the
network is built eagerly every time a model file is opened, which slows
everything down — it will be built only when first needed.

**`routing.py` (lake) — donor and consumer.**
It currently contains our *best* implementation of connection extraction
(it is the only one that handles both declaration blocks and the hand-off
recipes). That extraction logic is **promoted** out of the lake into the new
pyhspf topology builder — it is the reference implementation, not discarded
work. What remains in `routing.py` is exactly the lake's own business: stamp
rows with the run identity, compute the permanent row keys, and read/write
the warehouse tables.

**`edges.py` (lake) — retained as a thin catalog, derived not computed.**
Its purpose (a compact one-row-per-connection warehouse table) remains
useful. But it will no longer extract anything from model files itself: it
becomes a stored summary **derived from the same topology tables** (routing.py
already has a `connections_from_transfers` summarizer to build on). Its
duplicated vocabulary (two competing definitions of edge kind/role across the
two lake modules) is consolidated into one shared definition in the core
package, since "what kind of connection is this" is a single-model fact.

---

## 4. Implementation phases

Each phase is independently useful, independently testable, and leaves the
system working. Nothing below changes what reports or the warehouse produce
for a correct model — except where today's output is *wrong* (models using
the NETWORK block), and those changes are the point.

### Phase 0 — Safety net (≈ half a day)

**What:** Before touching anything, capture the current outputs of the
existing code across all 68 models: connection lists, drainage areas,
outlet lists, upstream/downstream answers. Store these as baseline files.

**Why:** Every later phase is judged against this baseline. Where new output
differs, the difference must be either (a) a documented bug fix or (b) a
NETWORK-block connection the old code missed. Any other difference fails the
phase. This converts "did the refactor break anything?" from an opinion into
a mechanical check. Our existing golden test suite provides the harness.

### Phase 1 — Housekeeping in graph.py (≈ half a day, low risk)

**What:** Delete dead code (~250 lines of commented-out experiments and an
unused class); fix the function that accidentally modifies data it reads;
make network construction lazy (built on first use instead of every file
open); make the module tolerant of blank numeric fields that currently crash
it on some models.

**Why:** Shrinks the surface area before the real surgery, removes booby
traps that would confuse later testing, and gives an immediate speedup to
every script that opens model files.

### Phase 2 — Build the shared topology builder (≈ 2–3 days, core of the plan)

**What:** Create a new module in the core package whose only job is: given
one parsed model file, produce the standard tables — operations,
connections (from **both** declaration blocks, with per-row receipts),
member transfers, and diagnostics for anything unresolvable. The
implementation is *extracted* from `routing.py`'s existing, most-complete
logic, then extended with the connection-level and diagnostic outputs the
other consumers need. Shared vocabulary (connection kind and role
definitions) moves here from the two lake modules.

**Why:** This is the single implementation everything else will trust. It is
written once, documented once, and tested once — against all 68 models, with
the reconciliation tests described in section 2. Nothing else is rewired yet;
this phase only has to prove the builder is right.

**Exit test:** For all 68 models, builder totals reconcile with raw-file
totals, and the builder's SCHEMATIC-only subset matches Phase 0 baselines.

### Phase 3 — Rewire graph.py onto the builder (≈ 1–2 days)

**What:** Replace graph.py's private extraction with "build the network from
the topology tables." The reporting interface stays identical. Run the full
baseline comparison.

**Why:** Reports immediately gain NETWORK-block awareness — drainage areas,
outlets, and upstream/downstream answers become correct for every model, not
just SCHEMATIC-only models. Expected baseline differences are exactly the
NETWORK connections; each one is reviewed and documented rather than assumed.

### Phase 4 — Rewire the lake catalogs (≈ 1–2 days)

**What:** `routing.py` drops its now-promoted extraction internals and calls
the shared builder, keeping only run-stamping, permanent keys, and storage.
`edges.py` becomes a derived summary of the same tables, and the duplicate
vocabulary is deleted in favor of the shared core definitions.

**Why:** After this phase there is provably one extraction implementation in
the codebase. Warehouse tables gain the same diagnostics (unresolvable rows
are recorded, not lost), and any future fix lands everywhere at once.

**Exit test:** Warehouse tables built before and after the rewiring are
identical for all models (the lake already handled both blocks, so no
NETWORK differences are expected here — a strong cross-check of Phase 2).

### Phase 5 — Downstream adopters (as those efforts proceed)

**What:** The UCI↔GIS validation campaign's adapter and the future forcing
generator consume the topology tables directly; cross-model connections are
implemented lake-side only, fed by the model inventory's linkage registry and
recorded via the existing cross-model field on the edge table.

**Why:** These were the efforts that would otherwise have created the fourth
and fifth parallel copies. Wiring them to the shared builder is now trivial,
and cross-model knowledge stays cleanly out of the core package — preserving
the option to split the lake into its own package with a one-way dependency.

---

## 5. Effort, risk, and what could go wrong

**Total effort:** roughly 5–8 working days spread across the phases, each
phase shippable on its own. No "big bang" cutover exists anywhere in the
plan; at every point the previous behavior is one revert away.

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| The new builder mis-reads some model's connections | Low–medium | Phase 0 baselines + reconciliation tests across all 68 real models; per-row receipts make any discrepancy traceable to a model-file line in minutes |
| Reports change output unexpectedly | Low | Interface is frozen; only *documented corrections* (NETWORK awareness, area-summing audit) may change numbers, each reviewed against the baseline |
| Warehouse tables shift identity/keys | Low | Permanent keys are computed in the lake layer, which is not being redesigned — only its input source changes, verified by before/after table comparison |
| Effort creep ("while we're in here…") | Medium | The plan deliberately excludes: adding external-input edges to the graph, cross-model routing implementation, and any new report features. Those are separate, later effort |

**The payoff, restated once:** one correct implementation instead of three
diverging ones; reports that are right for every model rather than most;
diagnostics instead of silent data loss; and a foundation that the GIS
validation campaign, the forcing generator, and the eventual lake package
split all consume for free instead of each re-inventing it.

---

## 6. Decision checklist for sign-off

1. Approve the ownership rule: single-model facts in `pyhspf`, multi-model
   and run-level facts in the lake layer (enables the future package split).
2. Approve promoting `routing.py`'s extraction logic into the core package
   as the single shared implementation.
3. Approve that reports may change numbers **only** where today's numbers are
   demonstrably wrong (NETWORK-block models; area-summing audit), with each
   change documented against the Phase 0 baseline.
4. Approve deferring cross-model routing to the lake/inventory layer,
   sourced from the model-linkage registry.

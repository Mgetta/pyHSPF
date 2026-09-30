# HSPF Model Inventory: Proposed Organization and Versioning Standard

**Status:** Draft for team feedback
**Date:** 2026-09-30

---

## 1. The problem we are trying to solve

We maintain roughly 68 HSPF watershed models. Each model consists of several
files that must all agree with each other, even though nothing in the files
themselves enforces that agreement:

- **UCI file** — the model control file. It defines the operations (PERLNDs,
  IMPLNDs, RCHRESs), their parameters, and how they are connected.
- **WDM files** — the input/forcing data (meteorology, point sources,
  withdrawals). The UCI references specific datasets inside these files by
  number.
- **HBN files** — the binary output files produced when the model runs.
- **Vector layer** (GIS file) — shows how the watershed was spatially lumped:
  which land areas became which PERLNDs, which stream segments became which
  reaches, and which meteorological zone each area belongs to.

The only thing holding these files together today is care and memory. The
reach numbers in the GIS layer must match the reach numbers in the UCI. The
met zone assignments in the GIS layer must match how gages are assigned to
operations in the UCI. The dataset numbers the UCI asks for must actually
exist in the WDM files. When any one file is updated — new met data, a
corrected spatial lumping, a recalibration — nothing tells us which other
files are now out of date.

On top of that, models change over time (updated forcing data, updated
spatial inputs, recalibrations) and models have parallel variations (a
standard implementation and a mercury implementation of the same watershed,
for example, both in active use). Today there is no standard way to tell
which files belong to which version of which model.

This document proposes a folder structure, a set of naming conventions, and a
small set of rules that make every model self-describing, portable, and safe
to manage by hand. It is deliberately designed to be maintainable **without
any special software** — automation and validation tools can be added later,
but nothing depends on them.

---

## 2. Design goals

These are the priorities the proposal was designed around, in order:

1. **Every model version is completely self-contained.** If you copy one
   folder, you have everything needed to understand and run that version of
   that model. There are no references to files living somewhere else that
   might have changed or moved.
2. **Sharing is trivial.** "Send the 2023 version of the Sauk model to DNR"
   should mean zipping one folder, and nothing more.
3. **Manageable by hand.** The scheme must work when the only tools are
   Windows Explorer and a text editor. Bookkeeping is kept to a bare minimum
   (a small text file or two per version, mostly written once).
4. **Mistakes are contained, not just discouraged.** If someone is
   interrupted halfway through an update, the previous version must still be
   intact and unambiguous.
5. **History is preserved.** Old versions remain available and identifiable,
   so we can answer "what did this model look like in 2023?" years later.
6. **Room to grow.** Provenance tracking, automated consistency checking, and
   inventory tooling can be layered on later without reorganizing anything.

---

## 3. Key terms

To keep the rest of the document unambiguous, here is exactly what each word
means in this proposal:

- **Model** — one watershed model as a concept, independent of any particular
  set of files. Example: "the Sauk River model." Each model gets a permanent,
  short identifier (its *model id*), such as `sauk_r03`.

- **Artifact** — one of the files that make up a model: a UCI, a WDM, a
  GeoPackage, etc.

- **Variant** — a named line of development for a model. Most models have
  only one variant, called `main`. Some models have parallel variants that
  are both in active use — for example, a `mercury` variant that simulates
  mercury while the `main` variant does not. Variants are *not* newer or
  older than each other; they are siblings that evolve independently. The
  name `main` means "the model's original main line" — a permanent
  historical fact, like the trunk of a tree — and never means "the variant
  you should currently use." (What happens when a different variant becomes
  the standard is covered below.)

- **Version** — a numbered snapshot *within* a variant. Versions within a
  variant are sequential: `main_v03` replaced `main_v02`. Versions across
  different variants are unrelated: `mercury_v01` and `main_v14` can both be
  current at the same time. A version freezes the **model core**: the input
  files plus the calibrated base UCI — in other words, *the model as it
  stood at that point in time*.

- **Scenario** — a *question asked of* a frozen model version, answered by
  running one or more alternative UCIs against the input files present in
  that version folder. For example: "what happens to loads under the 2035
  TMDL allocations?" A scenario is not part of what the model *is*; it is an
  interrogation of it. Scenarios live in an append-only `scenarios/` area
  inside the version folder (see below). Every version has one special
  scenario called `base`: the model's own calibrated, standard configuration
  — the UCI you run when you just want "the model," and the reference that
  all other scenarios are measured against. The base UCI is part of the
  model core, so it lives in the folder root rather than in `scenarios/`.

- **Case** — one UCI within a scenario. Many scenarios need only one UCI,
  but some need several: for example, attributing loads to point sources by
  generating one UCI per source with that source turned off, then
  differencing the runs. All of those UCIs are cases of one scenario,
  because together they answer one question.

- **Manifest** — a small text file (`manifest.yaml`) inside each version
  folder that records what the version is, when it was made, and what
  changed. It describes the model core and is written once.

- **Scenario log** — a small text file (`scenarios/scenarios.yaml`) inside
  each version folder that lists the scenarios asked of that version. Unlike
  the manifest, it is *append-only*: entries are added over time as new
  questions come up, but existing entries are never edited or removed.

The three concepts form a clean hierarchy, and it is worth internalizing:

| Axis | Answers the question | Lifecycle |
| --- | --- | --- |
| **Variant** | Which line of the model? | Coexisting; each maintained, each with its own version stream |
| **Version** | Which state of that line? | Superseding; write-once snapshots of the model core |
| **Scenario** | Which question asked of that state? | Append-only; anchored to one version, never evolving on its own |

### Where is the line between a new version and a new variant?

The boundary is **not** about how large the change is. A five-line parameter
edit and a complete re-lumping of the watershed can both be plain version
bumps. The deciding question is about what happens to the *previous* setup:

> **Versions supersede. Variants coexist.**
>
> Ask: "After this change, will the previous line still be used for new
> work?" If no — the new setup replaces the old one — it is a new
> **version**, no matter how large the change. If yes — both lines will be
> maintained and run going forward — it is a new **variant**, no matter how
> small the change.

Examples: updated met data, a recalibration, or a corrected spatial lumping
all *replace* what came before, so they are versions. Turning on mercury
simulation might be a tiny edit, but if the non-mercury model remains in
active use alongside it, it is a variant.

Secondary signs that something is a variant rather than a version: it
simulates different constituents; it serves a different purpose or audience;
it permanently needs input files the other line does not; you expect to
maintain both lines into the future. If none of those apply, it is almost
certainly just a version.

Finally, a reassurance: **misclassifying is cheap to fix.** Because every
version folder is self-contained (files reference each other by bare
filename only), reclassifying later means renaming the folder, renaming the
UCI files that carry the variant name, and updating two manifest fields.
When a case is genuinely ambiguous, pick one, write a clear note in the
manifest, and move on.

### Where is the line between a scenario and a variant?

A scenario is anchored to one frozen version and does not evolve — its
answers are meaningless apart from the exact model state it interrogated.
A variant has *its own future*: its own recalibrations, its own input needs,
its own maintenance expectations, its own version stream.

The practical rule of thumb: if the alternative runs against input files
already present in the version folder, it is a scenario. If it needs
different or additional input files, or a structurally different model
setup, it is a variant.

And the graduation clause: **a scenario becomes a variant the moment it
acquires its own future.** For example, a TMDL scenario that stops being a
"what if" question and becomes a permanently operated alternative
configuration — maintained, recalibrated, relied upon — should be promoted:
copy the version folder to a new variant line with the scenario's UCI as its
base (the standard variant-creation move in section 8).

### What if a variant becomes the new standard?

Suppose the `mercury` variant matures to the point that it, not `main`, is
the model everyone should reach for. It is tempting to want the folder names
to say so — but a name that encodes *status* ("current," "active,"
"standard") is guaranteed to go stale, because status moves, and renaming
frozen folders breaks everything that references them. The principle: a
name records what something permanently **is**; a status is a **pointer**
that lives in exactly one small place that is allowed to change. There are
two promotion cases, distinguished by the same supersede-versus-coexist
test:

**Case 1 — the old line is retired.** If nobody will use the non-mercury
setup for new work, the mercury line has stopped coexisting and started
superseding — and supersession is exactly what versions are for. The
mercury setup **folds back into the main line as its next version**: copy
the latest mercury folder to the main line's next version number
(`mercury_v05` → `main_v16`), with a manifest note recording the adoption.
Nothing is renamed, the `mercury_v01` through `mercury_v05` folders remain
as frozen history, and `main` remains truthfully the main line — because
the main line absorbed the winner. Most promotions are this case.

**Case 2 — both lines remain in active use, but mercury is now the
standard.** Only a designation changed, so it is recorded as a single
mutable pointer: a one-line optional file at the model folder root.

```yaml
# sauk_r03/model.yaml — present only when the standard variant is not "main"
standard_variant: mercury
```

This file is deliberately the opposite of everything else in the inventory:
it is *allowed* to change, because it carries no history — it is a pointer,
not a record. It is absent from most models (where `main` is the standard),
so it costs nothing until needed, and it migrates naturally into the
repository-level registry when that exists (section 10).

---

## 4. Proposed folder structure

```text
hspf_models/
├── linkages/
│   └── linkages.yaml                     # cross-model connections (see section 9)
└── models/
    └── sauk_r03/                         # one folder per model; name = model id only
        ├── model.yaml                    # optional pointer; present only when the
        │                                 #   standard variant is not "main" (section 3)
        ├── sauk_r03_main_v14.zip         # superseded version, compressed (optional)
        ├── main_v15/                     # current version of the "main" variant
        │   ├── manifest.yaml             # ┐
        │   ├── sauk_r03_spatial_v3.gpkg  # │ the MODEL CORE:
        │   ├── sauk_r03_met_v3.wdm       # │ write-once, defined when the
        │   ├── sauk_r03_point_v2.wdm     # │ version is created
        │   ├── sauk_r03_main_base_v8.uci # ┘ (the base UCI IS the model)
        │   ├── scenarios/                # the QUESTION SET: append-only
        │   │   ├── scenarios.yaml        #   the scenario log
        │   │   ├── tmdl2035/             #   a one-case scenario
        │   │   │   └── sauk_r03_main_tmdl2035_v1.uci
        │   │   └── ptloads/              #   a multi-case scenario: source
        │   │       ├── sauk_r03_main_ptloads-nowwtp1_v1.uci    # attribution by
        │   │       └── sauk_r03_main_ptloads-nowwtp2_v1.uci    # elimination runs
        │   └── workspace/                # run outputs; always safe to delete
        └── mercury_v02/                  # current version of the "mercury" variant
            ├── manifest.yaml
            ├── sauk_r03_spatial_v3.gpkg  # same file as in main_v15 (same name = same file)
            ├── sauk_r03_met_v3.wdm
            ├── sauk_r03_point_v2.wdm
            ├── sauk_r03_hgload_v1.wdm    # extra input that only this variant needs
            └── sauk_r03_mercury_base_v2.uci
```

Points worth noting:

- **The model folder name is the model id and nothing else.** Human-readable
  names ("Sauk River") change spelling and get disambiguated over the years;
  the folder name must never need to change. The readable name lives inside
  the manifest.
- **The version folder root holds the model core and nothing else**: the
  input files, exactly one UCI (the base UCI), and the manifest. With five
  to ten files, subfolders for "spatial" versus "forcing" add navigation
  without adding clarity — the filename suffixes (`_met.wdm`,
  `_spatial.gpkg`) already say what each file is. The only two subfolders
  are `scenarios/` (the question set) and `workspace/` (disposable outputs).
- **Each scenario is a subfolder under `scenarios/`**, named by the scenario
  and holding its case UCIs — one UCI for simple scenarios, several for
  scenarios answered by a set of runs. This is uniform: a single-UCI
  scenario is simply a scenario with one case.
- **There is no separate archive folder.** A superseded version folder simply
  stays where it is (optionally compressed into a zip file). The current
  version of each variant is the folder with the highest number — a
  convention that cannot go stale because it is computed from what exists,
  not recorded anywhere.
- **`workspace/` holds run outputs** (HBN, .out, .ech files). It is always
  safe to delete and is excluded when zipping or sharing a version.

---

## 5. Naming conventions

**Model id.** Short, lowercase, permanent. Once assigned, it never changes,
because it appears in every folder and file name.

**Version folders.** Named `{variant}_v{NN}` with a zero-padded two-digit
number: `main_v01`, `main_v15`, `mercury_v02`. The zero-padding keeps folders
listed in the correct order in Windows Explorer. Every model has at least the
`main` variant; additional variants get short descriptive names (`mercury`,
`pfas`, `climate2050`).

**Files: two naming families.** A file name records either what a file
permanently *is* (an **identity**) or which snapshot it belongs to (a
**coordinate**) — never a mixture, and never a status word like "current."

*Input artifacts (WDMs, GeoPackages) are named by identity:*
`{model_id}_{role}_v{N}.{ext}`, for example `sauk_r03_met_v3.wdm`. The role
token says what the file is (`met`, `point`, `spatial`), and the version
number is that file's own revision count — independent of any folder
version. The met data might be on its 3rd revision while the model is on
its 15th version, because most model versions change only one or two files.
Input names deliberately contain no variant and no folder version, because
an input file's identity does not depend on where it appears: if the main
and mercury variants use the same met data, that is one artifact, and it
carries one name in both folders.

*When two alternatives of the same input genuinely coexist, the role token
is qualified.* Suppose meteorological inputs are generated by two different
recipes and both are valid and in concurrent use. The supersede-versus-
coexist test from section 3 applies to input files exactly as it does to
model lines: if recipe B *replaces* recipe A, that is an ordinary version
bump of `met`; if they *coexist*, they are two different identities and get
qualified role tokens — `sauk_r03_met-nldas2_v3.wdm` alongside
`sauk_r03_met-prism_v1.wdm` — each with its own independent version counter.
Two guardrails: the qualifier must be an *identity* word that names the
recipe or source (`met-nldas2`, `met-scaled2050`), never a *status* word
(`met-new`, `met-alt`, `met-final`), and qualifiers should be introduced
only at the moment a second concurrent alternative actually exists — a
single lineage that improves over time is just version bumps of a plain
role. When a folder holds coexisting alternatives, the **base UCI defines
which one is canonical** (whichever file its FILES block reads); a scenario
may bind to the other alternative to ask "what does the model do under the
other forcing?"; and if use of the alternative matures into its own
maintained line with its own calibration, it graduates to a variant.
Retiring an alternative is effortless: the next version folder simply does
not carry the file forward, and the folder comparison makes the retirement
visible.

*UCIs are also named by identity — but a UCI's identity includes its
variant and scenario:* `{model_id}_{variant}_{scenario}_v{N}.uci`, for
example `sauk_r03_main_tmdl2035_v3.uci`. This is not an inconsistency with
the input rule: unlike a met file shared across variants, the mercury UCI
genuinely *is* a different artifact from the main UCI, so variant and
scenario are part of what it is. The pattern is uniform — every UCI carries
all three tokens, with nothing ever omitted. The base UCI is simply the
scenario named `base`: `sauk_r03_main_base_v8.uci`,
`sauk_r03_mercury_base_v2.uci`. (A name whose parts can be silently absent
cannot be read reliably by either people or programs, so no "shortened"
form is allowed.)

*Multi-case scenarios extend the scenario token with a hyphenated case
suffix:* `sauk_r03_main_ptloads-nowwtp1_v1.uci` is the `nowwtp1` case of
the `ptloads` scenario. This does not break the uniform pattern — a name
still has exactly one scenario token; the hyphen structure inside it is
meaningful to people and to the scenario log, and invisible to the
positional naming rules.

*Version folders, zip archives, and run outputs are named by coordinate*,
because each one is not an artifact with its own lineage — it *is* a
specific combination of model, variant, version, and (for runs) scenario:

| Thing | Pattern | Example |
| --- | --- | --- |
| Version folder | `{variant}_v{NN}` | `main_v15` (the model id comes from the parent folder) |
| Zip of a version | `{model_id}_{variant}_v{NN}.zip` | `sauk_r03_main_v14.zip` |
| Run output | `{model_id}_{variant}_v{NN}_{scenario}.{ext}` | `sauk_r03_main_v15_ptloads-nowwtp1.hbn` |

**Why every file repeats the model id.** Files escape their folders
constantly in practice — they get emailed, copied to someone's desktop,
attached to memos. A loose file named `met.wdm` is a mystery; a loose file
named `sauk_r03_met_v3.wdm` is self-identifying down to the exact version.

**Why per-file version numbers.** They let you see at a glance what changed
between two version folders. If `main_v14` and `main_v15` both contain
`sauk_r03_met_v3.wdm` but the spatial file went from `_v2` to `_v3`,
then the spatial data is what changed — no notes required, the folder
listing tells the story.

**Identical name means identical file — across all folders.** If
`sauk_r03_met_v3.wdm` appears in `main_v15` and in `mercury_v02`, those must
be byte-for-byte the same file. This is what makes the naming trustworthy.

**Names are checkable; the manifest is the truth.** These names are designed
so a future tool can read them mechanically — to cross-check a filename
against its folder and manifest and flag disagreements, and to recover the
model/variant/version/scenario coordinate from a run output, which carries
no manifest of its own. Three small rules keep the names readable by a
program:

1. Underscores separate the fields of a name. Therefore the variant,
   scenario, and role tokens must never contain an underscore — join words
   inside a token with hyphens instead (a linkage role is `from-sauk-r03`,
   never `from_sauk_r03`; a scenario case is `ptloads-nowwtp1`).
2. Model ids *may* contain underscores (`sauk_r03` is fine), because names
   are read from the right: the last token is the version, the fixed number
   of tokens before it (which depends on the file type) are the
   scenario/variant/role, and everything remaining is the model id.
3. The variant vocabulary and the scenario vocabulary must be **disjoint**:
   no word may ever be used as both a variant name and a scenario name
   anywhere in the repository. (`main` is reserved for variants; `base` is
   reserved for scenarios.)

For anything that both a name and a manifest state, the manifest is
authoritative; names exist for humans and for catching drift, not for being
the system of record.

---

## 6. The rules

Almost everything in this proposal is convention that tolerates sloppiness.
These rules do not — they are what the whole system rests on:

> **Rule 1 (the important one): The model core is write-once; the scenario
> area is append-only.**
> Once a version folder exists, no file in its root — inputs, base UCI,
> manifest — is ever edited, replaced, or deleted. If anything in the core
> needs to change, even a one-line edit to the base UCI, copy the folder to
> the next version number and make the change there. The `scenarios/` area
> is the deliberate exception, in one direction only: scenario UCIs and
> scenario-log entries may be **added** at any time, but never edited or
> removed once added. Revising a scenario means adding its next `_vN` file;
> the superseded file stays. (`workspace/` is outside the rules entirely —
> it is disposable.)

> **Rule 2: If you touch a file, bump the version in its filename.**
> Never edit `sauk_r03_met_v3.wdm` in place; the edited copy is
> `sauk_r03_met_v4.wdm`. An edited file with an unchanged name silently
> breaks the "same name = same file" guarantee for everyone.

> **Rule 3: UCIs reference files by bare filename only.**
> The FILES block in every UCI must use plain same-folder filenames
> (`sauk_r03_met_v3.wdm`), never absolute paths (`C:\projects\...`) or paths
> into other folders. This is what makes every version folder portable — it
> runs the same from a network share, a laptop, or a colleague's machine.
> (Scenario UCIs are run from the version folder root, or by tools that
> stage files together, so the same bare filenames work for them.)

> **Rule 4: Record every version in the manifest, and every scenario in the
> scenario log.** Facts go in fields; the story goes in the note (see
> section 7). Thirty seconds now; invaluable in three years.

The main failure mode to be aware of: Rule 2 depends on people, and a file
edited without renaming is currently undetectable. Section 10 describes how
automated checking (file fingerprinting) will eventually catch this; until
then, the rule is social, and it is the one to be most careful about.

One property consciously traded away: because the scenario area grows, a
version folder is no longer a fixed set of bytes over time — it is a fixed
model *core* plus a growing question set. Nothing ever changes meaning
(append-only means a zip taken last month is simply a subset of the folder
today), and the dates in the scenario log recover "what existed when" if it
ever matters.

---

## 7. The manifest and the scenario log

### manifest.yaml — describes the model core, written once

```yaml
model_id: sauk_r03
name: Sauk River
variant: main
version: 15
date: 2026-09-29
base: sauk_r03_main_base_v8.uci
note: "Relumped PERLNDs 141-143 into 141."
change_type: spatial-update
```

The guiding principle for this file:

> **Facts go in fields; the story goes in the note.** Any statement a tool
> would ever need to find or compare gets its own field. The note carries
> only the narrative — the *why* — in one or two sentences. And nobody
> restates what the folder listing already proves: *which* files changed is
> visible by comparing two version folders, so the note does not repeat it.

The always-present fields:

- **model_id / name** — the permanent identifier and the human-readable name.
- **variant / version** — repeats what the folder name says. The redundancy
  is intentional: it makes the folder self-describing even after it is
  zipped, renamed by accident, or copied somewhere else.
- **date** — when this version was created.
- **base** — the base UCI filename (the model's defining configuration).
- **note** — one or two sentences on why this version exists. Because every
  version folder carries its own note, the full history of a model is simply
  the notes read in order — no separate changelog document ever needs to be
  maintained.

The optional structured fields, present only when relevant:

- **change_type** — one word from a small controlled vocabulary:
  `recalibration`, `forcing-update`, `spatial-update`, `correction`,
  `import`, `branch`, `adoption`, `linkage-refresh`. Cheap to write, and it
  makes questions like "show me every recalibration across all 68 models"
  answerable by a tool someday.
- **branched_from** — on the first version of a new variant: the version
  folder it was copied from (`branched_from: main_v12`).
- **adopted_from** — on a promotion fold-back (section 3, case 1): the
  variant version that was adopted (`adopted_from: mercury_v05`).
- **imported_from** — on a version created by importing a pre-inventory
  model: the original location
  (`imported_from: 'X:\models\sauk\2021_update'`).
- **inflows** — on models fed by another model (section 9): structured
  provenance for each frozen linkage file:

  ```yaml
  inflows:
    - file: osakis_r02_from-sauk-r03_v2.wdm
      upstream_model: sauk_r03
      upstream_variant: main
      upstream_version: 15
      upstream_scenario: base
      run_date: 2026-09-29
  ```

- **schema** — a format version number for the manifest itself
  (`schema: 1`), so the file format can evolve safely later.

Because manifests are per-version and write-once, adding structure over time
creates **no migration debt**: old manifests stay exactly as they are, new
fields simply appear in new versions, and a tool treats a missing field as
"unknown." More structure (per-file fingerprints, input recipes) can be
added the same way later — see section 10.

### scenarios/scenarios.yaml — the scenario log, append-only

```yaml
scenarios:
  - scenario: tmdl2035
    date: 2026-10-04
    purpose: "Loads under draft 2035 TMDL point source allocations."
    cases:
      - {case: tmdl2035, file: tmdl2035/sauk_r03_main_tmdl2035_v1.uci}

  - scenario: ptloads
    date: 2026-11-12
    purpose: >
      Attribute TP loads to individual point sources: one run per source
      with that source turned off, differenced against the base run.
    reference: base
    cases:
      - {case: nowwtp1, file: ptloads/sauk_r03_main_ptloads-nowwtp1_v1.uci,
         change: "WWTP 1 discharge zeroed"}
      - {case: nowwtp2, file: ptloads/sauk_r03_main_ptloads-nowwtp2_v1.uci,
         change: "WWTP 2 discharge zeroed"}
```

Each entry records the question (`purpose`), the runs that answer it
(`cases`), and — for comparison-style scenarios — what the runs are
differenced against (`reference: base` means the base run itself serves as
the comparison, which is why the base UCI never needs to be copied into a
scenario folder). Entries are only ever added; superseding a case means
adding its next `_vN` file and a new case line. Scenario case UCIs are often
machine-generated, which tempts people to treat them as disposable — keep
them anyway: until generator tooling is inventoried, the file is the only
record of what was actually run.

---

## 8. How common tasks work

**Updating a model (new met data, recalibration, any change to the core).**
Copy the current version folder to the next number (`main_v15` →
`main_v16`), **without** the `scenarios/` and `workspace/` folders. In the
new folder: replace the changed file(s), bumping the version in their
filenames; update the FILES block in the base UCI if a WDM filename changed;
update `manifest.yaml` (version, date, note, change_type). The old folder is
never touched. If you are interrupted or make a mess, delete the
half-finished new folder and start over — the old version is intact by
construction.

**Worked example: a recalibration.** Suppose `sauk_r03/main_v15/` contains
`sauk_r03_main_base_v8.uci`, the met and point WDMs, and the spatial
GeoPackage. The hydrology is recalibrated against an extended gage record,
so only parameter values inside the base UCI change:

1. Copy `main_v15/` to `main_v16/`, leaving `scenarios/` and `workspace/`
   behind.
2. In `main_v16/`, rename the UCI to `sauk_r03_main_base_v9.uci` and make
   the parameter edits there. Every WDM and the GeoPackage keep their exact
   names, because they did not change. Comparing the two folder listings now
   shows precisely one renamed file — the calibration.
3. Update the manifest: `version: 16`, new date,
   `change_type: recalibration`, and a note such as `"Recalibrated PWATER
   (LZSN, UZSN, INFILT, AGWRC) to the 2015-2025 record at gage 05270500."`

This is a version, not a variant, because the new calibration replaces the
old one — nobody intends to keep using the old parameters for new work. It
is not a scenario, because a scenario is a question asked *of* the model,
while the calibration *is* the model.

Note what happened to the scenarios: **they were deliberately left behind.**
A scenario UCI embeds the parameter values of the version it was built
against, so carrying it forward would silently pair an outdated calibration
with the new model. The new version starts with an empty question set, and
each scenario that still matters is consciously regenerated against the new
calibration (as its next `_vN`) and logged. The old version folder keeps the
old scenarios, correctly paired with the model state they actually
interrogated.

(The rare exception that flips a recalibration into a variant: if, say, an
approved TMDL must continue to be run against the *old* calibration while
new work uses the new one, then both calibrations are in simultaneous active
use — that is coexistence, so the two lines become separate variants.)

**Asking a new question of an existing version (adding a scenario).** This
does **not** create a new version — nothing about the model changed. Create
a subfolder under `scenarios/` named for the scenario, add the case UCI(s)
— `sauk_r03_main_tmdl2035_v1.uci`, or for a multi-case study
`sauk_r03_main_ptloads-nowwtp1_v1.uci` and siblings — and append an entry to
`scenarios/scenarios.yaml` recording the purpose, the cases, and what they
are compared against. Nothing already in the folder is touched. Revising a
scenario later means adding its next `_vN` file and a new log line; the old
file stays as the record of what was run before.

**Bringing an existing model into the inventory.** Start from the model as
it is used *today*: assemble its current files into `main_v01`, renaming
them to the convention, and record where they came from with
`imported_from` and a note (for example, `"Files current as of 2026-09."`).
Do **not** try to reconstruct the model's history as version numbers — the
predecessors scattered around the shared drive (the original development,
the extension five years later) were each *superseded* by what followed,
which makes them old versions, not variants; but back-numbering versions
from memory creates false confidence. Leave predecessors where they are. If
one later proves worth preserving properly, import it as a frozen variant
named by era — for example `hist2008_v01`, with a manifest note saying it
is the original 2008 development, superseded by the current main line,
imported for reference and not maintained. That stretches the meaning of
"variant" slightly (it is a dead line rather than a coexisting one), but it
is an honest, self-describing home for history.

**Creating a variant.** Copy the current main version folder (without
`scenarios/` and `workspace/`) to the new variant's first folder
(`main_v12` → `mercury_v01`). Add or replace the files the variant needs,
rename the base UCI to carry the new variant token
(`sauk_r03_mercury_base_v1.uci`), and update the manifest
(`variant: mercury`, `version: 1`, `change_type: branch`,
`branched_from: main_v12`). From then on the variant evolves independently:
`mercury_v02`, `mercury_v03`, and so on, while `main` continues on its own
track. Both are current at once; neither supersedes the other.

**Promoting a variant to the standard.** See "What if a variant becomes the
new standard?" in section 3. In short: if the old line is being retired,
copy the winning variant's latest folder to the main line's next version
number and record the adoption (`change_type: adoption`,
`adopted_from: mercury_v05`) — the variant's old folders remain as frozen
history. If both lines stay in active use and only the designation changed,
record it in the model folder's one-line `model.yaml` pointer. Frozen
folders are never renamed in either case.

**Sharing a model.** Zip the version folder (excluding `workspace/`, and
excluding `scenarios/` unless the analyses are part of what is being
shared) and send it. The recipient gets a complete, runnable,
self-describing model with its manifest inside.

**Retiring old versions / saving disk space.** Compress superseded version
folders to zip files in place (`main_v14/` → `sauk_r03_main_v14.zip`). If
disk space becomes a real problem, the large WDM files can be deleted out of
very old versions while keeping the UCIs and GeoPackage — the UCIs are
small text files and are the heart of the model, so they should be kept
forever.

**Running a model.** Run it inside the version folder; outputs land in
`workspace/`, named by their full coordinate
(`sauk_r03_main_v15_base.hbn`, `sauk_r03_main_v15_ptloads-nowwtp1.hbn`).
Outputs are disposable here — the analysis-ready copies of model output
live in our separate results warehouse, keyed by the same
model/variant/version/scenario coordinate.

---

## 9. Cross-model linkages

A few models feed each other: an upstream model's outflow becomes an input
to a downstream model. In practice this works through a linkage WDM file —
the upstream model *writes* timeseries into it when it runs, and the
downstream model reads them as boundary inflows. That makes linkage files a
different kind of object from everything else in the inventory: every other
input file is authored by a person, but linkage contents are *produced by a
model run*. Handling them cleanly requires separating two things that
currently share the name "linkage file":

**1. The topology — a static contract.** "Sauk reach 30 outflow feeds
Osakis at a specific external-sources entry, via a specific dataset number."
This changes about as often as the models themselves do. It is recorded once,
at the repository level, in `linkages/linkages.yaml` — one entry per
connection, stating the upstream model and reach, the downstream model and
its entry point, and the dataset numbers involved. This file also implicitly
records run order: to refresh a downstream model, its upstream models must
run first.

**2. The payload — a run product.** The actual timeseries written into the
linkage WDM when a *specific version and scenario* of the upstream model was
run. From the upstream model's point of view this is output; from the
downstream model's point of view it is input forcing whose origin happens to
be another model rather than a gage network.

Once the payload is seen as "forcing data with unusual provenance," the
write-once rules already say what to do with it:

**The downstream model's version folder contains its own frozen copy of the
populated linkage file, treated exactly like any other input WDM.** For
example, the Osakis folder would contain
`osakis_r02_from-sauk-r03_v2.wdm` — named by the *downstream* model
(it is that model's input) with a role token recording which model it came
from (hyphens inside the role token, per the naming rules in section 5).
The provenance — which upstream version and scenario populated it, and when
— goes in the manifest's structured `inflows` field (section 7), never in
the filename, because it changes over time while a name must not.

Why duplicate rather than share one live linkage file between the two
models? Because a single shared file that the upstream model writes into and
the downstream model reads from is exactly the kind of silently-changing
shared state this whole proposal exists to eliminate. If Sauk is rerun, every
frozen Osakis version would quietly mean something different — with nothing
visibly changed in the Osakis folders. Duplication also keeps every
downstream model **standalone**: zip an Osakis version folder and the
recipient can run it without possessing the Sauk model at all, because the
boundary inflows are included as data. Linkage files are small, so the disk
cost is negligible.

**Day-to-day iteration does not create versions.** While actively working —
for example, calibrating both models together and rerunning the upstream one
many times — the chain runs happen in `workspace/` folders: the upstream
model writes its linkage output into its own workspace, and the working copy
of the downstream model reads from there. Only when the downstream model is
*frozen* into a version folder is the current populated linkage file copied
in and its provenance recorded. Versions capture decisions, not iterations.

**What this buys us: staleness becomes visible.** `linkages.yaml` says the
connection exists; the Osakis manifest says its inflows came from Sauk
`main_v15`; the Sauk folder shows its current version is `main_v17`.
Together those three facts reveal that Osakis may be out of date — a
question that is *impossible to ask* under a shared live file, because
nothing records what state the upstream model was in when the downstream one
last ran. Duplication does not prevent a downstream model from going stale
when its upstream is updated — that lag is inherent to a sequential
workflow — but it makes the lag recorded and detectable instead of silent,
which is the most an inventory can do.

Variants compose without any new machinery: if a mercury chain exists, the
downstream mercury variant folder simply carries its own linkage payload
copy, with provenance pointing at the upstream mercury version that
populated it.

---

## 10. What we are deliberately deferring

The scheme above is intentionally the minimum. The following are all
worthwhile, all compatible with this structure, and all postponed so that
the initial mental load stays low:

- **File fingerprints (checksums).** A future `manifest.yaml` can record a
  short digital fingerprint for each file, letting a tool detect the
  "edited without renaming" mistake automatically across all 68 models.
  Fingerprints can be backfilled for existing versions at any time.
- **Source provenance for split and generated files.** Several models draw
  on shared statewide sources (met data, hydrography), and qualified input
  roles (section 5) imply generation recipes. The long-term plan is a
  manifest `inputs:` section recording, for each input file, exactly which
  source file, which datasets, and which recipe produced it. That record is
  what will let us regenerate every affected model automatically when a
  statewide source is updated.
- **A repository-level registry.** A single `registry.yaml` listing every
  model, its display name, and its status (active / legacy / deprecated).
  It should be *generated* by scanning the manifests rather than maintained
  by hand, so it can never disagree with them. Until it exists, the folder
  listing under `models/` is the inventory. The per-model `model.yaml`
  standard-variant pointer (section 3) migrates into the registry when it
  exists.
- **An automated consistency checker.** A tool that opens a version folder
  and verifies the contract between files: reach ids in the UCI match the
  GIS layer, every dataset the UCI requests exists in the WDMs, the
  simulation window is covered by the forcing data, the FILES block points
  at files that exist, and linkage endpoints exist on both sides. Findings
  it raises that turn out to be intentional quirks get recorded as
  documented exceptions ("waivers") with a written reason — so the checker
  gets quieter and more trustworthy over time instead of being abandoned as
  noisy.
- **Inventory tooling.** Commands that automate the copy-bump-note update
  transaction, generate the registry, verify fingerprints, and generate
  scenario case UCIs from declared changes. The manual procedures in
  section 8 are designed to be exactly what the tools will later do, so
  adopting them changes nothing about the structure.
- **A shared file store (eliminating duplicate copies).** Copying an entire
  version folder when only a UCI changed duplicates large WDM files that did
  not change. A future refinement would keep every file exactly once in a
  single store folder, with version folders holding only their UCIs and a
  manifest listing which stored files they use; a tool command would then
  assemble ("flatten") a complete, runnable folder on demand for running or
  sharing — identical to today's version folders, so nothing changes at the
  boundaries. The naming convention already makes this migration mechanical,
  because "identical filename = identical file" means the filename itself is
  the reference. But this refinement is strictly gated on tooling existing
  first: without a tool, a store means folders that are no longer
  self-contained, references that can dangle when store files are deleted,
  and no cheap way to know whether an old version still needs a given file.
  (Filesystem shortcuts and links are not an acceptable substitute — an
  in-place edit through a link would corrupt every version at once.) Until
  then, the disk cost of copies is managed by zipping old versions and
  pruning WDMs from very old ones, and small UCI tweaks can be batched into
  a single version bump when nothing is urgent.

Nothing on this list requires renaming or reorganizing anything created
under the minimal scheme. That is the test the proposal was designed
against: start simple, grow without migration.

---

## 11. Summary of what we are agreeing to

1. One folder per model, named by a permanent model id.
2. Inside it, version folders named `{variant}_v{NN}`. Most models have only
   the `main` variant; parallel variants (e.g., `mercury`) are first-class
   and evolve independently, and multiple variants can be active at the same
   time. The boundary: versions supersede what came before; variants coexist
   with it. `main` means the original main line, never "the one to use" —
   when a variant becomes the standard, it either folds back into the main
   line as its next version or is designated by a one-line pointer file;
   frozen folders are never renamed.
3. Each version folder has a write-once **model core** (inputs, the base
   UCI, the manifest) and an append-only **scenario area** (questions asked
   of that frozen state, each scenario a subfolder of one or more case
   UCIs, logged in `scenarios.yaml`). Adding a scenario is not a version
   change; changing the core always is.
4. Input files are named by identity (`{model_id}_{role}_v{N}`, with
   hyphen-qualified roles when true alternatives coexist); UCIs by identity
   including variant and scenario
   (`{model_id}_{variant}_{scenario}_v{N}`, uniformly, with the base
   scenario named `base` and multi-case scenarios using hyphenated case
   suffixes); and folders, zips, and run outputs by their full coordinate.
   An identical filename always means an identical file, and the manifest —
   not the filename — is the system of record.
5. Facts go in manifest fields (`change_type`, `branched_from`,
   `adopted_from`, `imported_from`, `inflows`); the note carries only the
   narrative. Because manifests are write-once and per-version, structure
   can be added over time with no migration of history.
6. UCIs reference their companion files by bare filename, keeping every
   version folder fully portable.
7. Outputs go in a disposable `workspace/` folder; old versions get zipped
   in place; linkage topology is recorded once in a repository-level
   linkages file, while each downstream model carries its own frozen,
   provenance-stamped copy of the populated linkage data.

## 12. Open questions for feedback

1. Do the proposed model ids work for everyone, and who assigns them? (Ids
   may contain underscores, but variant, scenario, and role names must not —
   see the naming rules in section 5.)
2. Does "versions supersede, variants coexist" — and its scenario corollary,
   "a scenario becomes a variant when it acquires its own future" — resolve
   the ambiguous cases people actually encounter?
3. Is the split between a write-once model core and an append-only scenario
   area workable in practice, and is per-scenario subfoldering the right
   granularity for multi-UCI studies?
4. Is the starting `change_type` vocabulary (recalibration, forcing-update,
   spatial-update, correction, import, branch, adoption, linkage-refresh)
   right, and who maintains it?
5. Retention: is "zip old versions, keep UCIs and GIS forever, allow pruning
   WDMs from very old versions" acceptable? And should old scenario areas be
   pruned with their WDMs or kept?
6. Are there models whose current organization genuinely cannot be expressed
   this way (unusual file types, external dependencies that cannot be copied
   into the folder)?
7. Who owns `linkages.yaml`, and what should its exact format be?
8. For linked models: when an upstream model gets a new version, what is our
   expectation for how quickly downstream models are rerun and refrozen, and
   who is responsible for it?

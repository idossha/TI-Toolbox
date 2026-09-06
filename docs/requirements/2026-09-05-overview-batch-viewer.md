# Maintainer requirements — 2026-09-05

These are hard gates for the v3 overview / batch / terminal / guide / viewer pass. They refine
[ARCHITECTURE.md](../ARCHITECTURE.md) §§2–6 and **reverse** desktop/DESIGN.md §§9–10 where those
made Subjects the landing page, coupled a run page's 3D pane to the selected subject, and let the
Viewer load a scene from a selector change. Where an earlier plan conflicts, these requirements win
and the contract is amended with the implementation. The implementation plan of record is
[desktop/IMPLEMENTATION_PLAN.md](../../desktop/IMPLEMENTATION_PLAN.md) (R1–R5, gate tests).

## Asks, verbatim

1. "the first tab should not be subjects, it should be overview"
2. "We can also delete the subject info page completely and migrate bits and pieces of logic and information from that into the overview page."
3. "regarding the terminal in all pages, make sure that A it is scrollable, b that it can be cleared. Make sure the logic is modular and recyclable between all pages."
4. "all pages that require subject selection, they need to behave like the pre-processing does"
5. "users should be able to select multiple subjects for either a parallelized or a sequential processing"
6. "instead of actually rendering the selected individual, we can be rendering a general individual, for example, Ernie"
7. "the top [bar] will have more selection, for example the type of atlas and so on, and that it does not load information automatically based on subject selection"

## R1 — Replace Subjects with a project Overview

The first rail item, the ⌘1 target, the initial route, the catch-all destination, the palette's
first page and the page id are `overview`. Per subject it shows raw staged/converted, FastSurfer,
FreeSurfer, m2m, DWI, CT, leadfields, EEG nets and high-level totals for simulations, optimizations
and analyses; pending, absent, partial and failed are distinct states. Its facts come from one
`GET /api/catalog/overview` whose request count does not grow with subjects or simulations. Subject
Info — page, shim, panel id, Settings toggle and fixtures — is deleted; `/panel-subject-info` falls
through to `/overview`. Detailed output discovery stays lazy and owned by Results.

* Gate test: in mock projects of 3 and 30 subjects, opening Overview makes exactly one overview
  catalog request, renders every subject and every defined presence/count column, and ⌘1, first
  launch, catch-all, rail and palette all resolve to `/overview`. No Subject Info route or toggle is
  discoverable.

## R2 — Make the shared terminal scrollable and locally clearable

`ui/Jobs.tsx::JobConsole` remains the one interactive log renderer for all four run pages and the
Jobs rail, over one pure event→line and sequence-merge module. It gains a source-aware Clear that
hides the currently visible lines without deleting server events or truncating a log file.

* Gate test: a 100-line console has `scrollHeight > clientHeight`; one long line has
  `scrollWidth > clientWidth`; scrolling changes both offsets. Clear removes all current rendered
  lines, leaves the input array byte-for-byte unchanged, shows the next higher-sequence line, and
  does not carry its watermark to a different source key.

## R3 — Standardize subject selection and execution policy

`SubjectsField` is the only set selector and is open by default on Pre-processing, Simulator,
Optimizer, Analyzer and Source. Every workflow producing one independent job per subject exposes the
same `Subjects in parallel` control; the server, not request timing in React, enforces the cap.
Group Analyzer and statistics stay one job over the cohort and show no cap.

* Gate test: the shared selector shows on first visit everywhere; two subjects produce two plan
  rows; a cap of 1 never has two group members `running` and a cap of 2 reaches two; each generated
  config carries exactly its own subject id; the UI never substitutes client-side parallel POSTs.

## R4 — Use a fixed guide in workflow 3D panes

Simulator, Optimizer and Analyzer scene panes stop querying the selected subject and draw a
project-independent, immutable guide packaged with the installation. Subject-RAS sphere picking is
disabled on the guide, not approximately transformed.

* Gate test: changing selected subjects makes zero guide-manifest requests and zero remounts; the
  manifest's atlas/net ids equal the packaged catalog ids; every referenced asset resolves; each
  surface keeps the `TVSC1` limit of 3 MB and 150,000 triangles; a guide click cannot update a
  subject-RAS coordinate.

## R5 — Make Viewer selection explicit and load on command

The Viewer separates `draftSelection` from `loadedSelection`. The source bar gains a view Type
selector and the selectors that type takes. Editing a selector only dirties the draft; Load
validates, snapshots, issues exactly one view request and posts exactly one scene. A failed Load
keeps the last successfully loaded scene. Deep links prefill and never auto-load. `GET
/api/view/{kind}` gains an optional `atlas`; absent preserves current behaviour.

* Gate test: initial navigation and each draft edit issue zero view requests and zero scene loads;
  one Load issues exactly one request with the visible draft values and one scene-load message;
  atlas A and atlas B produce distinguishable requested ids; a failed Load keeps the previous scene
  identity; a deep link fills controls and issues zero view requests before Load.

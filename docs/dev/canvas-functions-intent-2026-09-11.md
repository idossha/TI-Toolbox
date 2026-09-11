# Canvas functions and shared forms — 2026-09-11 intent

This clarification refines [ARCHITECTURE.md §7.3](ARCHITECTURE.md#73-pipelines) and supersedes
the previous notebook mechanism. Prove it with direct-call notebook fixtures and focused hidden
form tests; user intent takes precedence over the former job-adapter design.

## R1 — Export ordinary scientific calls

> "it really just exports the functions in order"

Write explicit complete inputs and calls to existing functions in dependency order. No graph
representation, planner or job execution adapter appears in the executable notebook cells.

* Gate test: execute emitted cells against instrumented scientific functions; received nested
  configurations equal the authored inputs exactly, with subject-specific outputs passed forward.

## R2 — Reuse the dedicated settings

> "if they click on a node for simulation it pretty much needs to render the simulation settings"

Share controlled settings components with Simulator, Pre-processing, Optimizer and Analyzer.
Canvas supplies node configuration and bound subjects; it must not submit standalone page jobs
or mutate the dedicated page's drafts when settings change.

* Gate test: configure representative non-default options through shared controls, save/reload the
  node and compare exact payload values, retaining untouched nested settings.

## R3 — Keep each artifact discoverable

> "export it to the notebook directory of the project"

Canvas Save retains the native document in the pipeline directory. Notebook export uses the existing
project notebook store and refreshes the Notebooks page; repeated exports preserve previous files.

* Gate test: export through Canvas, read the stored notebook and find its exact name on the
  Notebooks page; exporting again creates a distinct name without replacing the first.

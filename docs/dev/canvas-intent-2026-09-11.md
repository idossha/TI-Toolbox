# Canvas fidelity — 2026-09-11 intent

The maintainer authorizes correcting the canvas as a graphical composition of existing jobs,
with reproducible notebook export. This intent guides the implementation; the current contract
remains [ARCHITECTURE.md §7.3](ARCHITECTURE.md#73-pipelines). It introduces no scientific algorithms.

1. Preserve the full saved configuration when opening, editing unrelated fields, saving and
   reloading a node. Gate test: exact equality of untouched nested values in round-trip fixtures.
2. Bind only the named upstream output to the named consumer input. Gate test: conflicting
   historical outputs cannot change the selected producer's resolved configuration.
3. Validate the actual runner configuration before presenting a runnable graph. Gate test:
   missing required scientific inputs produce node-specific issues and submit no jobs.
4. Export executable, editable notebooks using the same configurations and existing functions.
   Gate test: execute exported cells with instrumented scientific entry points and compare
   received configs/dependencies to the canvas plan, including non-default settings.
5. Keep the UI understandable: each processing node owns its settings; connections express
   dependencies. Gate test: offscreen configure/save/reload/export and invalid-input scenarios.

Use small incremental local checks, followed by affected integration checks before pushing main.
Live FEM runs and complex CI changes are outside this task. Report verification limitations.

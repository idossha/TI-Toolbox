# EEG study consolidation — 2026-09-13

[Architecture §13](../dev/ARCHITECTURE.md#13-reusable-eeg-and-array-analysis) owns the ongoing contract. This records the requested scope and acceptance evidence; [testing](../dev/TESTING.md) owns runtime limits.

The user requested a branch that moves reusable study functions into TI-Toolbox, with notebooks calling its modeling, simulation, cortical projection, source and cluster APIs. Study-specific outcomes, cohorts, figure composition and scientific contrasts remain downstream. The sleepTI pre-migration state is preserved as `v1.0-preliminary`.

| Requirement | Gate |
|---|---|
| Reusable functions accept arrays, explicit paths and settings | Pure graph/association/effect/atlas imports; no study paths or participant files |
| Preserve published calculations in downstream adapters | Frozen `v1.0-preliminary` synthetic parity, including null distributions, confidence intervals, source scoring and event policy |
| Safe defaults for new studies | Signed clusters remain separate; zero handling, rank-score convention, sampling and fiducial choices explicit |
| Reuse existing modeling and simulation APIs | Notebook imports/cells call existing preprocessing and simulation functions |
| Compute nonlinear field metrics before scalar morph | Independent cancellation fixture plus manual carrier-vector expectations |
| Do not reuse incomplete/stale projection caches | Required-field and SHA-256 input provenance tests |
| Notebook entrypoints are readable and contain no participant data | Valid output-free notebooks; execute the synthetic notebook |
| Full scientific reproduction remains separate | Rerun approved participant data in a compatible SimNIBS/MNE container before claiming manuscript numerical reproduction |

No REST, desktop, job schema or public release changes are requested. No dataset or FEM rerun is inferred from passing small-array tests.

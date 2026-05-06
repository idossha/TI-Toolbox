# Flex-Search Multi-Core: Why It Doesn't Accelerate

**Date**: 2026-04-23

## Summary

The `cpus` parameter in flex-search has no meaningful effect on optimization
speed. The dominant cost — serial `goal_fun` evaluation inside scipy's
`differential_evolution` — is never parallelized.

## Root Cause

### 1. `workers` is never passed to `differential_evolution`

In `tes_flex_optimization.py` (line ~1567), scipy's DE is called without the
`workers` parameter:

```python
result = differential_evolution(
    self.goal_fun,
    x0=...,
    strategy="best1bin",
    ...
    seed=self.seed
)  # no workers= argument → defaults to workers=1 (serial)
```

### 2. What `cpus` actually controls (minor)

- **Numba thread count** (`set_num_threads`) — only helps if numba-JIT'd
  functions are used internally
- **Geodesic calculations** (`get_geodesic_destination(n_cpu=...)`) — runs
  only during electrode coordinate transforms, a tiny fraction of runtime
- **OnlineFEM init** — passed to the FEM solver (PARDISO), which may use
  threads for the linear solve but each solve reuses a pre-factored matrix
  and is already fast

## Why scipy `workers=N` won't work here

Scipy's `differential_evolution(workers=N)` uses `multiprocessing` to
evaluate multiple candidates in parallel. But `goal_fun` is a bound method
on `TesFlexOptimization`, which holds:

- `self._ofem` — OnlineFEM with pre-factored FEM matrix (not picklable)
- Mutable counters (`self.n_test`, `self.n_sim`)
- Large mesh data structures

These objects cannot be pickled (required by multiprocessing) and the FEM
factorization is too expensive to duplicate per-process.

## Realistic Options

1. **Parallelize multi-start restarts** — `flex.py` runs N DE restarts
   sequentially (`for i in range(n)`). Each restart creates its own
   `TesFlexOptimization` object. These are independent and could run in
   parallel across processes for near-linear speedup.

2. **Custom DE loop with thread-level FEM parallelism** — Replace scipy DE
   with a manual DE that generates the population, evaluates serially (shared
   FEM), but maximizes thread parallelism within each FEM solve. Marginal
   gains.

3. **`updating='deferred'`** — Prerequisite for `workers>1` in scipy DE
   (evaluates entire population before updating). Still blocked by the
   pickling problem.

## Recommendation

The most practical path is option 1: parallelize the multi-start loop in
`flex.py` using `multiprocessing.Pool` or `concurrent.futures.ProcessPoolExecutor`.
Each restart is fully independent.

## References

- `resources/map-electrodes/tes_flex_optimization.py` — SimNIBS optimization class
- `tit/opt/flex/flex.py` — multi-start orchestration loop
- `tit/opt/flex/builder.py` — builds SimNIBS objects from FlexConfig
- scipy docs: `differential_evolution(workers=...)` requires picklable objective

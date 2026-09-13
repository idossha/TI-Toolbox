# Optimizer candidate review — proposed implementation, awaiting approval

Base: main `3ab120f9`. Branch: `codex/optimizer-candidate-review`.
This is an approval proposal, not a claim that Flex is validated end to end. It refines
ARCHITECTURE §3 (subject-space preview), §5 (real-library verification), and the optimization
execution contract. Existing contracts remain effective until implementation is approved;
approved changes must amend the contract and decision log with their tests.

## User intent

> “before we do that I want to push what we have on main right now to main and then I want to create a branch or a walk tree whatever you prefer and walk on it there and make sure the flex is logical end to end”

> “if it won't take much more, why not? It will be it will be nice to have even if it's not optimized. It will be a good knowledge, good data to have.”

> “Come up with a plan of actions if we have logical bugs, surface them with me, and suggest a plan for execution for me to approve.”

Prior requested outcome: browse Ex and Flex alternatives by objective/intensity/focality,
preview their montages, and explicitly select one for simulation. The linked TIP v4/v5 videos
are design inspiration, not authorization to change optimization algorithms.

## Evidence and defects to address

- Flex restart selection checks `< inf` but calls argmin on the unfiltered array. A mixed
  finite/NaN array can select NaN; negative infinity is also accepted. Source: flex.py:188–205.
- Invalid placements return finite penalty 2.0, so finite score alone cannot prove validity.
  A run containing only invalid trials must fail, rather than becoming a usable candidate.
- Mean calibration uses abs(best_value); it accepts NaN, infinity and positive invalid penalties.
  Source: drivers.py:74. Require a valid mean evaluation with explicit sign/provenance.
- Scalar mutation 0.7 accepted by the builder fails at installed SimNIBS tuple conversion.
  Reproduced against installed code without a FEM run.
- Unequal ellipse axes become an average-radius circle. Actual installed ElectrodeArrayPair
  preparation confirmed that declared dimensions are unused in this path.
- Configured gel thickness is recorded but final Flex session creation omits thickness;
  installed helper defaults to [1,2] mm. Verify the intended layer mapping before correction.
- Pareto chart says higher is better while selection minimizes. Scores from different threshold
  objectives are not directly comparable as a common-metric Pareto frontier.
- Alternative restart/sweep folders are discarded; score history lacks matching poses.

Runtime evidence: installed tes_flex_optimization, electrode_layout, and onlinefem sources were
hash-identical to audited copies in the existing SimNIBS 4.6 container. Scalar mutation and ellipse
preparation were exercised there. 172 focused host tests pass but miss these integration gaps.
No full Flex run, numerical replay, performance benchmark or historical-result impact study ran.

## R1 — Correctness before candidate browsing

Fix valid-trial tracking, finite winner selection, mean calibration, and scalar mutation handling.
Bind the selected current split to the accepted candidate, including polish and multistart paths.
Treat overlap/rejected trials explicitly, not via a magic score threshold. Correct Pareto labels.
Gate test: mixed finite/NaN/±infinity and all-invalid trials cannot select an unusable winner;
invalid calibration raises; scalar and interval mutation both reach installed optimizer setup;
accepted candidate pose/current IDs match across fixed-ratio, ratio, restart and polish fixtures.

## R2 — Faithful geometry and replay

Persist realized 4x4 subject-space electrode poses, channel/array/electrode identity, signed
currents, shape, dimensions, material/layer thickness, and mesh/config provenance. Preserve
orientation for rectangular electrodes. Initially reject unsupported unequal ellipse dimensions
with an explicit explanation rather than silently changing shape; true ellipse support is a
separate choice. Wire configured gel thickness only after confirming layer semantics in SimNIBS.
Gate test: a non-square rotated electrode and an asymmetric-current montage round-trip with
position/current numeric error <=1e-9 in serialized units; actual SimNIBS session receives the
same orientation and intended thickness. This tolerance is proposed for metadata, not FEM fields.
Scientific correction notes must identify affected versions/configurations and rerun guidance.

## R3 — Observation metrics without changing the optimization goal

Add non-target observation sampling for intensity-only runs, separate from objective ROIs.
Default proposed domain: eligible GM in the same surface/volume domain, excluding target;
record tissue, resolution, weighting, envelope and domain explicitly. Existing explicitly chosen
avoidance regions remain separately identified. Do not combine these as a generic focality metric.
Start with ROI mean, ROI p99.9, background mean/p95 and a named target/background contrast.
Keep the actual objective distinct. Ex's existing volume-weighted whole-GM ratio and Flex's
non-ROI p95 contrast retain different labels. Prefer consistent weighting for new comparable
observation metrics; never silently rewrite old objectives to match them.

Installed OnlineFEM solves potentials before iterating ROIs: added sampling needs no additional
potential solve, but adds setup/interpolation/envelope/memory. Raw two-carrier fields alone cost
48 bytes per extra sample; mapping/gradient/temporary allocations add more. Ratio-search should
compute observation envelopes only for its chosen split when background does not affect scoring.
Do not turn on stock track_focality indiscriminately: its AUC scans thresholds 500 times.
Gate test: observation on/off leaves objective, chosen current split, valid-candidate set and FEM
solve count unchanged for deterministic fixtures. Empty/nonfinite observations produce missing
metrics and diagnostics without poisoning the original valid objective.

Benchmark: serial fixed candidate set on one real head model, surface and volume ROI, fixed and
searched current ratios. Measure preparation, potential solve, interpolation, envelope, reductions,
AUC, peak RSS and output size separately. Proposed default budget for approval: median evaluation
time <=10% and peak RSS <=20% above baseline. If exceeded, return with measured options before
choosing approximation, sparse sampling or finalist-only metrics. These are proposed budgets,
not measurements. Expensive AUC remains optional pending evidence.

## R4 — Durable candidate history

Record only valid evaluated trials; optionally count rejection reasons separately. Stream a
versioned CSV of scalar metrics and a companion full-precision pose record keyed by stable IDs.
Keep every restart/sweep's records before temporary-folder cleanup; mark completion/cancellation.
Never store raw field arrays for every candidate. Record returned objective, direction, threshold,
current split and declared-versus-realized geometry. Candidate count and objective history are
not evidence of an exhaustive search.
Gate test: interrupted recording leaves parseable complete records; candidate IDs join metrics
and poses one-to-one; invalid trials cannot be replayed; all restarts survive cleanup. Enabling
recording produces the same accepted result under fixed seed and solver settings.

## R5 — One reusable candidate browser

Provide a sortable/paginated candidate table and selectable intensity/background trade-off plot,
linked to the existing subject-space Simulator montage preview. Show channel colors, currents,
electrode locations and optional orientation. Label unavailable metrics and optimization estimates.
Plot only candidates evaluated with comparable anatomy/metric definitions; compute nondominance
from common measured metrics, not raw objectives with different thresholds. Call it the frontier
among evaluated candidates, not a guaranteed global Pareto frontier.

Use in Simulator creates a normal editable job with the selected candidate's exact configuration;
no auto-run. Preserve source provenance and warn if edits invalidate displayed candidate metrics.
Ex reads existing CSVs; historical Flex offers its saved winner only, with no fabricated history.
Gate test: hidden UI table/plot selection identifies the same candidate and preview; row selection
transfers exact geometry/current to the standard simulation plan. Large libraries stay within
bounded scroll panels, with empty/error/legacy states tested.

## R6 — End-to-end validation and delivery

Proceed incrementally: regression fixture first, narrow implementation, focused tests, then one
serial real Flex smoke and selected-candidate simulation on a copied test subject. Independently
recompute logged metrics from saved evaluated samples/reference fixtures, and compare final
remeshed simulation separately rather than demanding identical online/final fields. Establish and
review scientific tolerances before declaring numerical equivalence.
Gate test: subject → optimization → candidate → preview → simulation → analysis provenance is
traceable; observed and final metrics are explicitly distinguished; cancellation/retry and all-invalid
failures are handled. Build and normal repository gates pass. No branch merge without approval.

## Video inspiration (transcript review)

- [TIP v4](https://www.youtube.com/watch?v=SdPq3yBl9xI): supports the idea of exposing diverse
  alternatives and interactive trade-offs. Proposed here: table/plot/preview selection. Its surrogate
  optimizer is a separate research project and is outside this plan.
- [TIP v5](https://www.youtube.com/watch?v=b83VfRLEpEk): supports carrying model and selected
  configuration into detailed simulation/analysis. TI already keeps project data local; this plan
  adds no cloud upload or anonymization claims. Their performance claims were not independently
  verified and do not predict TI-Toolbox performance.

## Approval requested

Approve R1–R6 with benchmark-gated background metrics, optional AUC, explicit rejection of unsupported
unequal ellipses, and geometry/thickness corrections documented as scientific changes. Implementation
has not started; the branch currently holds planning only.

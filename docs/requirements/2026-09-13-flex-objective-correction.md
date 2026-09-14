# Flex objective and completed-log correction

This correction refines ARCHITECTURE §13 and supersedes the objective presentation in the earlier
candidate-review requirements. Deterministic authored fields establish the numerical definitions;
transport tests establish terminal log behavior. Historical study values are not new validation.

## R1 — Preserve the three scientific objectives

> mean TImax -> maximizing average TImax in the ROI
> max TImax -> maximize 99.9% TImax in the ROI
> Focality -> defined as the mean TImax in ROI/Non-ROI

Display Mean TImax, Max TImax (99.9%), and Focality. Focality maximizes
`mean(ROI)^(1+w) / mean(non-ROI)`, retaining `intensity_weight` in [0,1]. Zero is a pure ratio;
one additionally favors ROI intensity, while still penalizing the background. Store the definition
with new candidate histories; old p95 objectives and measurements retain their original meaning.

* Gate test: real NumPy/SimNIBS tests use ROI samples 0..1000 and non-ROI [1,1,1,5], whose authored
  means and linear percentile distinguish all three objectives. Weight endpoint ranking reversal,
  equal field scaling, and invalid inputs are tested independently. Percentile roundoff tolerance
  is 1e-12; no search-convergence claim follows from these formula tests.

## R2 — Settle the log after job completion

> it seems like the raw log keep on running even after the searched finished

Job success must follow worker exit. The terminal must preserve the final saved log, avoid replaying
old events on reconnect, and stop live updates once the authoritative completed log is loaded.

* Gate test: overlapping subscribers and reconnects do not reset event cursors; a terminal transition
  retains the final tail and rejects stale replay. Check the reported job's actual worker and saved
  log independently to distinguish UI replay from continued computation.

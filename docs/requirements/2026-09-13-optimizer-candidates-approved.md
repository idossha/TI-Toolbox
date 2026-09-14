# Optimizer candidate review — approval and focality simplification

Supersedes the pending approval state of [the original proposal](2026-09-13-optimizer-candidates.md).
The maintainer approved R1–R6 on 2026-09-13 and authorized serial real-data tests on project `000`
using ernie, 101, or LA. Work remains on `codex/optimizer-candidate-review` until reviewed;
this approval does not authorize merging the new optimizer implementation to main.

## Additional direction

- New desktop Flex jobs expose intensity and threshold-free contrast, with no user-specified focality
  thresholds. Existing threshold-based configurations remain readable and explicitly identified as
  legacy; never silently change their objective.
- Threshold-free contrast needs independent checks for nonfinite, zero and invalid background values.
  A solver stopping or returning a finite score is not proof of convergence or scientific quality.
- Present valid evaluated candidates, their recorded metrics and subject-space montage geometry.
  The displayed frontier is limited to evaluated candidates in the same metric domain.
- Selecting a candidate creates an editable standard simulation draft; it never launches computation.
  Preserve electrode geometry, orientation, currents and source provenance.
- Background observation for intensity remains benchmark-gated under the original time/RSS budgets.
  If the budgets fail, report the measurements before adopting approximate or sparse alternatives.

## Acceptance

The original R1–R6 gates still apply. Report real-library analytic checks separately from real-head
optimization, selected-candidate simulation and performance measurements. Short smoke runs are not
convergence validation. New outputs must not overwrite existing subject results.

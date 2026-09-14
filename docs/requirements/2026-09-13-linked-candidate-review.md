# Linked optimization candidate review

This request refines ARCHITECTURE §13. It changes review presentation, not optimization scoring.
Earlier scientific definitions and historical provenance remain authoritative.

> it will be nice ... scattering all the iterations on intensity focality scale ... beside the table
> users can basically click on dots ... or on the table lines and it will all be connected

## R1 — Link the table, scatter plot and existing montage preview

Show a scrollable candidate table beside an intensity–focality scatter plot. Selecting either
selects the same candidate, highlights its table row and plot point, and updates the existing
subject-space montage preview. Use the existing renderer; no separate 2D projection system is
required. The selected candidate remains the one sent to an editable Simulator draft.

* Gate test: hidden UI tests select by row and point, including a point outside the first table
  page, and assert a shared candidate ID, highlighted row, displayed montage and exact draft.
  Numeric layout assertions require separate columns on a desktop viewport.

## R2 — Show recorded evidence without inventing missing measurements

The plot spans loaded recorded candidates, independent of table pagination. Show loading,
limits and missing/comparison-incompatible measurements explicitly. Frontier membership describes
only comparable recorded points; it is not proof of a global Pareto optimum. Mean/Max runs without
background observation cannot acquire focality retrospectively. Historical p95 definitions remain
labeled separately from mean-denominator focality. Invalid placements have no fabricated dots.

* Gate test: fixtures exceeding one table page, missing metrics, incompatible definitions and
  failed loading assert counts and honest states. Frontier tests include ties and dominated points.

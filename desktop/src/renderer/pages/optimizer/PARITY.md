# Parity checklist — Optimizer (Flex / Ex / mEx), the merged page

Supersedes `pages/optimizer-flex/PARITY.md` and `pages/optimizer-ex/PARITY.md`, both deleted with
their directories. Parity sources: `tit/gui/flex_search_tab.py` (`FlexSearchTab`),
`tit/gui/ex_search_tab.py` (`ExSearchTab`, 2 656 lines, TI/mTI modes),
`tit/gui/components/{roi_picker,electrode_config,solver_params}.py`.

Legend: **[x]** built · **[~]** built with a documented deviation · **[→]** moved to another page ·
**[ ]** not built (gap, listed at the bottom).

## 0. What the merge did (program U7, DESIGN.md v3 §9)

Two nav entries copied from the PyQt tab strip became one page `optimizer` (⌘4, per orchestrator
decision Q5). The Method segment `⟨Flex │ Ex │ mEx⟩` is the first row of the work pane; the right
pane is the shared `RunPanel` (lane B2) with `kind` following the segment and
`jobKinds={["flex","ex","mex"]}` so the terminal follows whichever search you last started.

| was | is now |
|---|---|
| `pages/optimizer-flex/index.tsx` (page `optimizer-flex`, ⌘4) | `pages/optimizer/index.tsx`, Method = Flex |
| `pages/optimizer-ex/index.tsx` (page `optimizer-ex`, no shortcut), tabs Ex / mEx / Results | same page, Method = Ex / mEx; **Results tab → the Results page** |
| `optimizer-flex/config.ts` | `optimizer/flexConfig.ts` (unchanged) |
| `optimizer-flex/api.ts` + `optimizer-ex/queries.ts` | `optimizer/api.ts` |
| `optimizer-ex/{lib,ExForm,MExForm}.ts(x)` state + builders | `optimizer/exConfig.ts` |
| `optimizer-ex/roi/RoiPicker.tsx` (a local stand-in) | **deleted** — its two modes are now modes of the ONE `pages/_shared/roi` picker |
| `optimizer-flex/{ElectrodeParams,HyperParams,FocalityOptions}.tsx` | `optimizer/FlexSections.tsx` |
| `optimizer-ex/{ElectrodeBuckets,LeadfieldPanel,HelpButton}.tsx` | `optimizer/ExSections.tsx` |
| `optimizer-{flex,ex}/PlanPanel.tsx` (two hand-rolled plan cards) | `pages/_shared/run/{RunPanel,PlanGrid}` |
| `optimizer-ex/ResultsPanel.tsx` | **deleted** → `pages/results` (U4: ex/mEx runs are outputs, and `outputsTree.ts` already reads `getExRuns`/`getExRunResults`) |

## 1. Control-by-control: where every control went

### Shared (all three methods)

- [~] **Subject.** Was a `SubjectPicker` multi-select card (flex) and a `Select` (ex). Now the
      shell's context-bar switcher (U6, §2.3 "batch selection stays in the switcher popover"): the
      page reads `useSubject().selection`. Flex still batches across that selection (one
      `POST /api/jobs` per subject, tagged `flex-batch`); **Ex/mEx run for the primary subject
      only**, because the leadfield they need is resolved per subject — unchanged from the old
      page, which had a single-subject `Select`.
- [x] **Run name** (`ExConfig.run_name` / `MExConfig.run_name`) — was Ex-only; now the first row
      beside the Method segment for all three. Flex ignores it (`FlexConfig` has `output_folder`,
      left `null` exactly as before).
- [x] **ROI definition — one picker.** `pages/_shared/roi`'s `RoiPicker`, with `modes` per method:
      flex `["cortical","subcortical","spherical"]`, ex/mEx `["saved","subcortical"]`.
      `saved` is a **new fourth mode** of the shared picker (this lane), carrying what the old ex
      picker's "Sphere" page carried: the saved-ROI checkbox list, Add ROI dialog, delete
      confirmation, radius, coordinate space and the Combine checkbox.
- [x] **Overwrite confirmation** (`AlertDialog` on `will_overwrite`) — one dialog for all three.
- [x] **Plan** — one `RunPanel`. For Ex/mEx the grid's **columns are the run targets** (one per
      ROI target) rather than stages, so a three-ROI ex-search shows three columns of one chip
      each; for flex there is one column, the run.
- [x] **⌘⏎** runs the primary (`useRunShortcut`); the primary is never silently disabled — it
      reports `blockedReason` (§4.2 r8).

### Flex-search

- [x] Optimization goal (`goal_combo`) — same four options and wording → **Objective**.
- [x] Post-processing method (`postproc_combo`) → **Objective**.
- [x] Focality mode (Manual / Adaptive / Pareto), threshold text, adaptive ROI/non-ROI shares,
      Pareto threshold lists **and the live combination count** → **Objective**, shown only for
      `goal=focality`; the threshold-free help + intensity weight only for `focality_tf`.
- [x] Non-ROI definition method + the non-ROI `RoiPicker` (mode-synced to the ROI picker) →
      **Objective**.
- [x] Electrode current, shape, dimensions (x, y), gel thickness, min electrode distance,
      "optimize current ratio" + ratio levels, ratio total current → **Electrodes** (collapsible,
      value summary in the header). Electrode parameters stay in an electrode section, not the
      solver box (memory `feedback_gui_param_placement.md`).
- [x] Optimization runs, max iterations, population size, tolerance, mutation (min, max),
      recombination, CPUs → **Solver** (collapsible).
- [~] Anisotropy type / max ratio / max conductivity, skin-region margin, landmark exclusion, skin
      visualization + its net → **Solver ▸ Advanced**. (Was "Basic parameters ▸ Advanced" and
      "Hyper parameters ▸ Advanced"; two Advanced disclosures for one solver was one too many.)
      Anisotropy is still `scalar`/`vn` only — see gap 5.
- [x] Run final electrode simulation, run simulation with mapped electrodes + EEG net →
      **After the search** (collapsible, closed by default).
- [x] `POST /api/validate/{kind}` before submit; errors render in a `Callout` in the work pane
      (was: inside the plan card, which §4.5 reserves for the plan's own warnings).

### Ex-search

- [x] Leadfield list + "Create New" → the **precondition strip** under the Method segment: net
      select, a size chip when the leadfield exists, and `⚠ required` + `Generate (≈40 min)` when
      it does not (wireframes §4: "a hard prerequisite is a gate, not a form field").
- [~] "Refresh List" / "Clear" / "Refresh" leadfields buttons — still not built; react-query keeps
      both lists live, as in the predecessor.
- [ ] "Show Electrodes" dialog — still not built (unchanged gap; the names are visible in each
      bucket's picker).
- [x] Search space radio (Bucketed / All combinations) → **Electrodes**.
- [x] Four buckets E1±/E2± (`MultiSelect` chips from the net's electrode list) → **Electrodes**.
- [x] All-combinations pool → **Electrodes**.
- [x] Total current, current step, channel limit (Qt defaults 2.0 / 0.2 / 1.6 kept) → **Current**
      (collapsible; its header summary states the resulting split count).
- [x] Saved-ROI list, Add ROI dialog (name + `CoordinateInput` + subject/MNI), delete
      confirmation, ROI radius (1–10 mm, step 0.5, default 3.0), Combine checkbox, coordinate-space
      radio → the shared picker's **`saved`** mode.
- [~] Atlas ROI page → the shared picker's **`subcortical`** mode. Behaviour fix: the atlas entry
      now carries the atlas's real `atlas_path` resolved from `/api/catalog/atlases`, where the old
      local picker put the atlas **id** in that field.

### mEx-search

- [x] Eight buckets E1±…E4± → **Electrode pairs**.
- [x] Pair current, carrier wiring (`MTI_CHANNEL_ARCHITECTURES` + its help), force left/right
      symmetry (+ help), symmetry pairing → **Carriers** (collapsible).
- [x] "Combine ROIs" is hidden on mEx (`allowCombine={false}`), exactly as the Qt tab unchecked
      and disabled it — now expressed as the control not existing rather than existing dead.
- [ ] `symmetry_eeg_csv` override — still not built (no Qt widget; inferred from the leadfield).
- [ ] mEx pool mode (`MExConfig.PoolElectrodes`) — still not built; not in the Qt tab either.

## 2. New in the merge

- [x] **Search-cost read-out.** `cost.ts` computes it and the page prints it in two places that
      cannot disagree: beside the control that changes it (`Electrodes` / `Electrode pairs` /
      `Solver`) and in the action-bar digest.
  - Ex: `N electrodes · M splits · K combinations`, where `M` counts the two-channel splits
    `c1 = k·step` with both `c1` and `total − c1` inside the channel limit, and `K = montages × M`.
  - mEx: `N electrodes · 4 pairs · K combinations` (`+ " before symmetry"` when the symmetry search
    is on, because the pruning factor depends on the net's mirror map and the client cannot
    compute it). **Deviation from wireframes §4**, which asks for a `TRIPLETS` tile on mEx: mEx
    searches four *pairs*, not triplets, so a TRIPLETS number would be a fiction. Reported.
  - Flex: `population P × G generations [× R runs] [× S sweeps] ≈ N solves`.
- [x] **Status cells** (§11.1): `lastJob` and `planCost`, registered with `useStatusCells`.
- [x] `data-tier="1"` on the always-open sections (Method row + precondition strip, Target, and
      the method's first section) so `firstScreenControls` can measure them.

## 3. Gaps (not this lane's to fix)

1. **`flex_adaptive` / `flex_pareto` have no runner.** Unchanged from the flex page: the
   orchestration lives in the PyQt GUI thread, never as one subprocess. The page still submits
   those kinds with a provisional `adaptive` / `pareto` block; they work against the mock and will
   not run for real until the runner and the wire shape land.
2. **`JobGroupRequest.kind` is the literal `"pre"`.** A flex batch is still N individual
   `POST /api/jobs` calls tagged `flex-batch`, not one group.
3. **`blocked` is derived by string-matching warnings** (orchestrator decision on u0 Q2, accepted
   for 3.0). The follow-up is a structured `PlanResult.blocked: [{subject, stage, reason}]`.
4. **The Ex/mEx leadfield precondition is not yet a `blocked` chip.** Wireframes §4 says an unmet
   leadfield "is `blocked` in the plan matrix while it is unmet"; today the plan is simply not
   requested without a leadfield (no config to plan), so the grid shows the `blockedReason` line
   instead. Making it a chip needs a plannable config without a leadfield, i.e. a server change.
5. **Anisotropy type**: Qt offers `scalar`/`vn`/`dir`/`mc`; `FlexConfig`'s docstring documents only
   the first two. Still built with two.
6. **`disable_mapping_simulation`** — schema field, hardcoded `false`, as in Qt.

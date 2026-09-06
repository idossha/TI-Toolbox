# Critic — round 1 (after the build + FXU1/FXU2 fix round)

Method: fresh offscreen captures via `TIT_E2E_RUN_ID=critic-30421 bash scripts/e2e-quiet-check.sh npx
playwright test tests/e2e/screens.spec.ts` (5/5 green, 48 captures, both themes × both sizes × all
12 rail pages). The wrapper printed FAIL naming one window — `Electron … TI-Toolbox` at
`1919,1052 1024×1029` — which is off to the side at an x-origin past any 1280/1440 test viewport and
is the maintainer's own dev window per the ground rules, not a window this run raised; every capture
test itself passed (`frontmost after == frontmost before`, 19–71 samples clean per run). Read all 48
PNGs plus `metrics.json`; for anything ambiguous, read the component/CSS source directly and computed
contrast myself from `ui/tokens.css`'s literal hex values (script below), rather than trust the
existing `tokenContrast.test.ts`, which only covers `--on-accent`/`--on-danger` on filled buttons —
not the soft-chip pairs this round actually uses. No repo files modified; two `npx playwright test`
runs only (`screens.spec.ts`, then `settings.spec.ts smoke.spec.ts` as a keyboard/shell sanity check,
also green, 10/10).

Artifacts read: `desktop/tests/e2e/artifacts/critic-30421/*.png` + `metrics.json`.

---

## Findings

### 1. HIGH — five Panel pages violate "no page header outside Settings and Help" (checklist §12.4 item 2)

`PageLayout header={<PageHeader title="…" purpose="…" />}` is set in all five panel pages:
`src/renderer/pages/panels/source/index.tsx:193`, `.../subject-info/index.tsx:157`,
`.../cluster-permutation/index.tsx:203`, `.../nilearn-visuals/index.tsx:131`,
`.../nifti-group-average/index.tsx:130`. Measured directly by the shared instrument:
`metrics.json` → `panel-source` and `panel-subject-info` both report `"pageHeaderHeight": 48` at
both 1280 and 1440 (every other page in the run — `subjects`, `preprocess`, `simulator`,
`optimizer`, `analyzer`, `results`, `viewer`, `jobs` — reports `0`; `settings`/`help`, the two
documented exceptions, report `28`, i.e. even the allowed exception is a smaller header than what
the panels render). Screenshots: `panel-source-light-1280x800.png` and
`panel-subject-info-light-1280x800.png` show a 24 px bold title ("Source" / "Subject info") plus a
14 px purpose sentence directly under the context bar — visually identical in weight to the
Settings/Help headers DESIGN.md §2.3 and §9 name as the *only* two pages allowed one.

This is not a leftover from before this round — it is freshly *reachable* because of this round's
own fix: FXU2 item 1 (`fxu2-shell-browse-notes.md` §1.1) corrected `app/registry.ts` so a
`panel-<id>` page gets a real rail slot instead of being force-hidden; before that fix, the registry
bug hid every panel page from the rail regardless of the `Settings ▸ Feature panels` toggle, which
incidentally hid this header violation too. The fix was correct (the toggle now works, per its own
Settings screenshot: "Optional tools shown under Panels in the nav"), but it also means these five
headers are now on a review-visible path for the first time.

It also means DESIGN.md §9's stated target architecture — "There is no 'Panels' group…every optional
panel is a *mode* inside a page…`panel-subject-info` folds into Subjects, `panel-source` into
Pre-processing, the three analysis panels into Analyzer" — was never implemented; the panels still
ship as five fully independent `PageLayout` pages with their own nav rows and their own headers,
and the in-app Settings copy documents that as intentional ("shown under Panels in the nav"),
contradicting §9's prose outright.

**Fix**, in order of correctness vs. cost: (a) do the §9 fold (delete the five standalone pages,
move their forms into Subjects/Pre-processing/Analyzer as sections) — the documented target, or (b)
at minimum drop `header={<PageHeader .../>}` from all five `PageLayout` calls the way the v2
regression was removed from Subjects/Simulator/Results, and update §9's prose to describe the
panels as they now actually ship (separate rail rows, no header) rather than leave a written plan
nobody executed. Either way, `pageHeaderHeight` should read `0` here the same as everywhere else in
the rail.

### 2. HIGH — `--field` chip text fails WCAG AA contrast in the *light* (default) theme

`.chip-field { background: var(--field-soft); color: var(--field); }`
(`src/renderer/ui/components.css:171-174`). Computed from the literal light-theme hex in
`ui/tokens.css` (`--field:#E25B22`, `--field-soft:#FCE9E0`): **3.11:1**, well under the 4.5:1 floor
DESIGN.md §3.2/§8 and checklist item 5 require for normal text (chip text is 11 px
`.text-micro`/`.text-eyebrow`, not large text, so 4.5:1 is the applicable threshold, not 3:1). Dark
theme is fine (`#FF8A5B` on `#3A1E12` = 6.58:1) — this is a light-only failure, which matters more
than usual because light is the *default* theme (program U9, DESIGN.md §7).

Real, currently-shipping usage, not a theoretical pairing: `src/renderer/pages/results/index.tsx:670`
renders `<Chip kind={b === "TI" || b === "mTI" ? "field" : "neutral"}>` for every simulation row's
kind badge — visible today in `results-light-1280x800.png` as the orange "TI"/"mTI" tags beside
"Thalamus", "L_Insula", "docs_example" — and `src/renderer/pages/analyzer/ResultsPanel.tsx:177`
(`<Chip kind="field">{selectedAnalysis.field}</Chip>`) for the Analyzer's selected-field badge.
`tokenContrast.test.ts` does not test this pair (it only tests `--on-accent`/`--on-danger` on solid
fills), so nothing caught it.

**Fix**: darken `--field` and/or lighten `--field-soft` in the *light* block only (dark already
passes and per DESIGN.md §7 must not be touched to fix a light-only bug). A quick check: `#C24A16`
on the existing `#FCE9E0` clears 4.65:1. Recommend adding `field on field-soft` (and the other
chip-soft pairs below) to `tokenContrast.test.ts` so this class of regression is caught by the gate
that already exists for buttons.

### 3. MEDIUM — `--warning` chip text narrowly fails the same test, light theme only

Same computation, same file (`components.css:163-166`): `--warning:#9A6412` on
`--warning-soft:#FBF0DA` = **4.42:1** vs the 4.5:1 floor — a 0.08 miss, likely imperceptible to most
readers but a real, measurable AA failure on the default theme. Dark theme passes clearly (7.62:1).
Visible today on the Subjects readiness chips (`subjects-light-1280x800.png`: "MNI152 — no raw MRI",
"101 — no leadfield", "MNI152 — no leadfield", "MNI152 — no simulations") and would apply to the
Plan grid's `overwrite` chip (§4.5 table) the moment a fixture exercises one — this run's captures
happened not to show an `overwrite` cell, so the failure is proven from tokens, not from a captured
screenshot of that specific chip.

**Fix**: nudge `--warning` a shade darker or `--warning-soft` a shade lighter in the light block;
same `tokenContrast.test.ts` addition as finding 2 would catch both at once.

### 4. MEDIUM — nav-rail breakpoint contradicts DESIGN.md/§9/U7 in three places; the real decision lives only in a code comment

Shipped behaviour, confirmed both by the metrics (`nav: 56` for *every* page at 1280×800, `nav: 216`
for every page at 1440×900 — not just the Viewer) and by
`src/renderer/app/NavRail.tsx:15` (`LABEL_RAIL_QUERY = "(min-width: 1440px)"`): the label rail
appears only at ≥1440. But:

- DESIGN.md §2.1's "Exact widths" table (line 73) states `nav rail (labels; icons on the Viewer) |
  216 (Viewer 56) | 216 (Viewer 56)` for **both** 1280×800 and 1440×900 — i.e. every page but the
  Viewer should show labels already at 1280.
- DESIGN.md §2.2's breakpoint table (line 100) says the rail switches "below this width," naming
  **1280** as the breakpoint, not 1440.
- DESIGN.md §9 (line 577): "Icons + labels at ≥ 1280; icons + tooltips below." — again 1280.
- `dev/notes/v3-ui-program.md` U7 (line 25): "Icons + labels at ≥ 1280; icons at < 1280."

All four of those say the switch is at 1280. The code disagrees by a full breakpoint tier, and it
knows it disagrees — `NavRail.tsx:8-14`'s own comment calls this "the program's Q1" and reasons
about it in detail (216 px rail at 1280 leaves only 1064 px of content and the Viewer's embed needs
≥1200), and `tests/e2e/_helpers.ts:87` and `tests/e2e/screens.spec.ts:113-114` both cite "program
Q1" as the place this was decided, with the assertion itself baked to the *shipped* number
(`expect(subjects!.panes.nav).toBe(width >= 1440 ? 216 : 56)`). But grepping both DESIGN.md and
`v3-ui-program.md` for `Q1` returns nothing — the decision exists nowhere either document cites,
which is exactly what "docs are the single source" (this program's own house rule, `v3-ui-program.md`
line 12) exists to prevent. The reasoning in the code comment is sound and I am not asking for the
*behaviour* to change (every page gaining 160 px of content width, and the Viewer needing no special
case, is a real improvement over the letter of U7) — I am asking for the documents to say what the
app does. As written today, anyone reading DESIGN.md's own acceptance tables to check a 1280×800
screenshot (exactly what my brief asked me to do) is checking against numbers three places state
and the shipped app contradicts.

**Fix**: update DESIGN.md §2.1's table, §2.2's breakpoint row, and §9's sentence to read 1440, and
either inline the "Q1" reasoning from `NavRail.tsx` into one of them or add a short "Q1" line to
`v3-ui-program.md` §0 the two test comments can actually point at.

### 5. MEDIUM — one "recon-all" fallback string still ships

`describePreStageDir()` (`src/renderer/pages/preprocess/index.tsx:140`):
`if (/freesurfer/i.test(dir)) return "FreeSurfer recon-all (legacy)";` — a real, user-facing label
(used for a Plan-grid stage column / row tooltip, per the function's own doc comment two lines above
and `stageLabelFor` at line 146) that contains exactly the wording my brief and DESIGN.md §12.4 item
9 both call out as banned. It doesn't fire in this round's mock fixture — `fastsurfer` is checked
first (line 138) and every subject in the fixture uses FastSurfer-named directories, so no capture
in `critic-30421` shows it — but it is live, reachable code, kept explicitly for "an older backend"
whose directories still use classic FreeSurfer naming, i.e. exactly the population most likely to
have a real legacy project on disk today.

**Fix**: drop "recon-all" from the label — e.g. `"Structural segmentation (legacy)"` — the
`(legacy)` qualifier alone already carries the intended meaning without the retired tool's name.

### 6. LOW — the Terminal has no section label of its own

DESIGN.md §4.5's own wireframe (line 322) shows the right pane's second block headed `TERMINAL` the
same way the first is headed `PLAN` (visible in every screenshot as an 11 px eyebrow — see
`preprocess-light-1280x800.png`). `JobTerminal.tsx:212-249`'s actual header renders only the
source-specific text (`Last run · <file>`, `What will run · N steps · ~time`, or the followed job's
identity `pre · ernie · running 4m12s`) with no leading "TERMINAL" word anywhere in the component.
There is a 1 px rule separating it from the Plan grid above, so the boundary is visible, and every
one of those header states is legitimate description text — this is a pure hierarchy/labeling
nicety, not a broken rule, which is why it's Low rather than Medium.

**Fix (optional)**: a small `TERMINAL` eyebrow above the existing header line would match the
wireframe and give the pane the same two-part visual rhythm as PLAN above it. Not required.

### 7. LOW — mock warning copy reads as a CLI flag, not GUI prose

`tests/mock-server/server.mjs:633,651`: `"output already exists; pass overwrite to replace it"` —
rendered verbatim in the Plan grid's warning callout (`preprocess-light-1280x800.png`: "⚠ Before you
run this / output already exists, pass overwrite to replace it"). "Pass overwrite" is command-line
phrasing (as if to a flag), not the sentence-case GUI voice DESIGN.md §6 rule 8 and checklist item 9
ask for elsewhere in the same panel. Grepped the real server (`tit/server/routes/plan.py`) — it
never actually generates this string; no `warnings.append(...)` call there produces this or similar
copy for the exists/overwrite case, so this exact sentence is fixture-only, invented for the mock,
not yet-written production copy. Low severity because it's not shipped user copy today, but it's
what every future screenshot and every future contributor will copy from as "the known-good example"
until the server grows its own copy for this warning.

**Fix (optional)**: reword the fixture to the GUI voice now, e.g. "output exists and will be
overwritten" or "existing output will be replaced," so the reference text in the mock matches the
standard the rest of the panel is held to.

---

## What is good

- **Dead-space work is real and DOM-proven**, not just described. Every screenshot in every state I
  opened had a legibly populated right pane — no blank box anywhere, including the Terminal's three
  states (live/file/preview all correctly labelled per `data-source`). `firstScreenControls.hidden`
  is empty on all four run pages at 1280×800 in this run's own numbers, matching the notes.
- **Status bar discipline is airtight.** I read every page's status row in both themes at 1280 and
  found zero placeholder dashes anywhere — a page with nothing to say (Simulator/Optimizer/Analyzer
  with a blocked plan and no running job in this fixture) simply shows nothing on the left, exactly
  per §11's rule, rather than a stale or fake cell. Confirmed this is *correct* behaviour, not a bug,
  by reading `useRunStatusCells.ts` and the optimizer page's parallel implementation — both null out
  `planCost` when `plan.blockedReason` is set and `lastJob` when no job in this fixture's registry
  matches, which is exactly the right call given the data.
- **Truncation and paths are right.** Every long path I found (Results tree rows, Plan grid tooltips)
  truncates from the left with an ellipsis prefix and renders in mono, matching checklist item 4
  precisely — e.g. `…ives/SimNIBS/sub-ernie/Simulations/Thalamus` in `results-light-1280x800.png`.
- **Dark-theme parity is excellent.** Every pair of light/dark screenshots I compared side by side
  (preprocess, simulator, jobs, results, settings, subjects) matched layout pixel-for-pixel with only
  token-driven colour differences — no literal light-only colour, no missing dark treatment, no
  layout shift between themes anywhere I looked.
- **Freeview/Gmsh/X11 are genuinely gone from the live UI**, not just relabelled — I grepped the
  whole renderer tree and the only hits are (a) dead API-schema comments (`schema.d.ts`, not
  rendered), (b) code comments explaining the removal (not rendered), and (c) the Help ▸
  Acknowledgments citations for FreeSurfer and Gmsh as third-party libraries the pipeline actually
  depends on — legitimate scholarly credit, not the retired "Open in Gmsh/Freeview" actions, and
  correctly kept. The one real miss is finding 5 above (recon-all).
- **Keyboard and shell mechanics are solid.** Re-ran `smoke.spec.ts` and `settings.spec.ts` fresh in
  this session (10/10 green, quiet) — ⌘K palette, the jobs-rail toggle, ⌘⇧I right-pane collapse, and
  cross-page navigation shortcuts all work and are asserted on DOM state, not screenshots.
- **The Plan grid's own chip vocabulary is clean.** One legend, only the chips actually present in
  the current plan, no ad-hoc colours, no repeated "Output" labels — the specific v2 defect U3 was
  written to prevent is gone.

---

## Contrast pairs computed (from `ui/tokens.css` literal hex, WCAG relative-luminance formula)

| pair | light | dark | 4.5:1? |
|---|---|---|---|
| `--field` on `--field-soft` | `#E25B22` / `#FCE9E0` = **3.11:1** | `#FF8A5B` / `#3A1E12` = 6.58:1 | **light fails** |
| `--warning` on `--warning-soft` | `#9A6412` / `#FBF0DA` = **4.42:1** | `#F0B95B` / `#3A2C10` = 7.62:1 | **light fails (narrow)** |
| `--ink-3` on `--surface-2` | `#6B7784` / `#EEF2F6` = 4.06:1 | `#7D8A97` / `#1E2630` = 4.33:1 | fails both, but I found no shipped component that actually places ink-3 text on a surface-2 ground (checked table headers — those use `--ink-2`, which passes) — not reporting as a finding, flagging only as a latent trap for the next page that does |
| `--success` on `--success-soft` | `#177A47` / `#E1F3EA` = 4.66:1 | `#5BCB8A` / `#12301F` = 7.05:1 | pass |
| `--danger` on `--danger-soft` | `#B42318` / `#FAE3E0` = 5.36:1 | `#F28B7D` / `#3B1714` = 6.65:1 | pass |
| `--lost` on `--lost-soft` | `#7C3AED` / `#EDE4FD` = 4.64:1 | `#B794F6` / `#2C2145` = 6.08:1 | pass |
| `--accent` on `--accent-soft` | `#1F5BD7` / `#E6EEFC` = 5.09:1 | `#7FA6FF` / `#1B2A4A` = 5.96:1 | pass |
| `--ink` / `--ink-2` on `--surface` / `--surface-2` | 6.47–16.96:1 | 7.16–14.29:1 | pass everywhere |

Only the two flagged rows (findings 2, 3) are below 4.5:1 among pairs actually used as text-on-fill
in shipped components.

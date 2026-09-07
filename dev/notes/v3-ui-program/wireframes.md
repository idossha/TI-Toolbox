# v3 wireframes — eight pages at 1280 × 800 and 1440 × 900

> Historical. Kept for the per-page ASCII layouts and empty-state copy, which
> live nowhere else. Its §9 dead-space ceilings are superseded by
> `desktop/DESIGN.md` §12.3; the program narrative is
> `dev/notes/v3-program-history.md` § 2026-09-03 — UI program.

Companion to `desktop/DESIGN.md` v3 (§2 layouts, §4.5 run panel, §4.6 terminal, §9 nav, §10 viewer,
§11 status bar, §12 dev loop) and to the decisions U1–U10 in `dev/notes/v3-ui-program.md`. Every
frame below is what a build lane implements; every number under a frame is what its round measures.

**Scale.** Horizontally **1 character = 10 px**, so a 1280 window is 128 characters and a 1440
window is 144. Vertically the frames are compressed — each band carries its real px height in the
margin. Chrome that is identical on every page (context bar 40, jobs rail 32, status bar 24) is
drawn once, at the top of this file, and elided as `⟨chrome⟩` afterwards.

**Shared chrome, drawn once (1280 wide).**

```
┌──────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  TI  │ example ⌄  ›  ernie ⌄                                    ⌕ Search ⌘K  ● connected      3 running     │ 40  context bar (U6)
├──────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│      │                                                                                                      │
│ nav  │                          C O N T E N T   B O X        1064 × 704 at 1280 × 800                       │
│ 216  │                                                       1224 × 804 at 1440 × 900                       │
│      │                                                                                                      │
├──────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ● running  pre ernie ▓▓▓▓░░ 62% 4m12s   ● queued sim 101              +3 more                            ⌃ │ 32  jobs rail (⌘J → 260)
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Job pre · running 4m12s │ Plan 2 jobs · 8 CPU · 16 GB              ● connected │ tit 3.0.0 · api v1         │ 24  status bar (§11)
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
   nav rail: Subjects · Pre-processing · Simulator · Optimizer · Analyzer · Results · Viewer · Jobs
             ─────────  Settings · Help          (flat, no group headers, no subject id — U7)
```

---

## 1. Subjects — shape B, two-pane

The data home. Presence chips live **here** and nowhere else (U6). Full-width table; the detail pane
appears only when a row is selected, and the table takes its 360 px back when nothing is.

### 1280 × 800 — populated, row selected

```
│ nav  │ work pane                                                704 │ detail                        360 │
├──────┼────────────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ ▣ Su │ ┌ raw 3/3 ███ ┬ recon 1/3 █░░ ┬ m2m 3/3 ███ ┬ dwi 1/3 █░░ ┐   │ ernie                             │ 40  coverage strip: 4 tiles
│ ▤ Pr │ └──────────────┴───────────────┴──────────────┴──────────┘   │ ───────────────────────────────── │ 24
│ ⚡ Si │ 3 subjects   ⌕ Filter…        ⟨All│Ready│Incomplete⟩  + Add  │ Head model  m2m · charm 4.6       │ 28  toolbar
│ ◎ Op │ ─────────────────────────────────────────────────────────── │ Surfaces    recon-all 7.4.1       │ 28  header row
│ ▦ An │ SUBJECT  RAW FS FSR M2M DWI CT  LEADFIELD    SIM OPT ANLY   │ Leadfield   GSN-185 · 2.0 GB      │
│ ▥ Re │ ernie     ●  ●  ●   ●   ●  ○   GSN-185        3   2    5  › │ Volumes     847 213 nodes         │ 28  rows
│ 👁 Vi │ 101       ●  ○  ○   ●   ○  ●   —              1   0    0  › │ ───────────────────────────────── │
│ ☰ Jo │ MNI152    ○  ●  ○   ●   ○  ○   —              0   0    0  › │ RECENT                            │
│ ──── │ (20 rows fit at 800; 26 at 900)                              │ ✓ sim  Thalamus       2 h  open › │
│ ⚙ Se │                                                              │ ✓ flex L_Insula       1 d  open › │
│ ? He │                                                              │ ✗ ex   E2E_Target     2 d  log  › │
│      │                                                              │ ───────────────────────────────── │
│      │                                                              │ [Simulate] [Optimize] [Analyze]   │ 28  four verbs
│      │                                                              │ [Open in viewer]                  │
```

**Empty state** — no subjects in the project: a centred whole-page `EmptyState`, one sentence
("This project has no subjects yet."), one primary (`Add subjects`). The coverage strip and the
detail pane are **not rendered**.
**No row selected:** the detail pane is not rendered; the table is 1064 px wide.

### 1440 × 900

```
│ nav  │ work pane                                                                    864 │ detail      360 │
```
Same bands; the table gains the `LAST ACTIVITY` column (a relative time) at 864 px and 26 rows fit.

**Numbers this lane hits** — dead space ≤ 25 % populated, ≤ 30 % with no row selected (v2 today:
**88 %**); `panes.right` is `360` with a selection and **`0`** without; status cells
`counts = "3 subjects · 3 m2m · 1 leadfield"` only.

---

## 2. Pre-processing — shape A, run panel

The page the program was written against: a 300 px Plan card beside 900 px of nothing.

### 1280 × 800 — two subjects selected, a run in flight

```
│ nav  │ work pane                                     666 │┃│ run panel                          360 │
├──────┼───────────────────────────────────────────────────┼─┼─────────────────────────────────────────┤
│ ▣    │ SUBJECTS                              2 selected  │ │ PLAN                                 ⟳ │ 24
│ ▤ ►  │ ☑ ernie   ●raw ●fs ●m2m ●dwi ○ct                 │ │ ┌──────┬──────┬───────┬──────┐         │
│ ⚡    │ ☑ 101     ●raw ○fs ●m2m ○dwi ●ct                 │ │ │ JOBS │ CPUS │  MEM  │ WAITS│         │ 40  stats strip
│ ◎    │ ☐ MNI152  ○raw ●fs ●m2m ○dwi ○ct                 │ │ │   2  │   8  │ 16 GB │   1  │         │
│ ▦    │ ───────────────────────────────────────────────── │ │ └──────┴──────┴───────┴──────┘         │
│ ▥    │ STRUCTURAL                                        │ │        dicom  charm   fs    tissue     │ 24  matrix header
│ 👁    │ ☑ Convert DICOM to NIfTI                          │ │ ernie   new    new    new    new       │ 24  one row / subject
│ ☰    │ ☑ SimNIBS charm (m2m + subject atlas)              │ │ 101     new   over…  skip   wait       │ 24
│ ──── │ ☑ FastSurfer segmentation      threads ⟨ 8 ⟩       │ │ new · skip · overwrite · blocked · wait│ 20  legend, once
│ ⚙    │ ☑ Tissue analyzer                                  │ │ ⚠ 101 — charm output exists and will   │
│ ?    │ ───────────────────────────────────────────────── │ │   be replaced.                         │     warnings callout
│      │ DWI (docker)                                      │ │ ⚠ 101 — queues behind job #12 (charm). │
│      │ ☐ QSIPrep     [Configure…]                         │ ├─────────────────────────────────────────┤
│      │ ☐ QSIRecon    [Configure…]                         │ │ TERMINAL  pre·ernie·running 4m12s ⌕⇩⧉ │ 24  header
│      │ ☐ Extract DTI tensor                               │ │ 12:04:01 INFO  charm: meshing …        │
│      │ ───────────────────────────────────────────────── │ │ 12:04:09 WARN  low contrast in T2      │     fills, min 180
│      │ ▸ EXISTING OUTPUTS      skip · logs derivatives/…  │ │ 12:04:11 INFO  charm: 847 213 nodes    │
│      │                                                    │ │ 12:04:18 INFO  fastsurfer: 12 % …      │
├──────┼───────────────────────────────────────────────────┤ │ 12:04:20 DEBUG cached T1 hash 9f2a…    │
│      │ 2 jobs · 8 CPU · 16 GB · 1 overwrite · 1 wait      │ │ ▁▁▁▁ follow-tail on ▁▁▁▁               │
│      │                            [ Queue 2 jobs   ⌘⏎ ]  │ │                                        │ 44  action bar
```

The form is **one column** at 666 px (the `.form-grid` container query fires at 760).

**Empty state** — no subject ticked: the run panel keeps its header, and where the strip and matrix
would be it renders two lines — *"Select a subject to see the plan."* + ghost `Choose subject ⌘P` —
left- and top-aligned. The Terminal below shows *"No run yet for this page."* The pane is never
blank and never shows dashes.

### 1440 × 900 — same page, two-up form

```
│ nav  │ work pane                                                      770 │┃│ run panel        400 │
│      │ ☑ Convert DICOM to NIfTI          ☑ SimNIBS charm (m2m + atlas)   │ │  (identical bands,   │
│      │ ☑ FastSurfer   threads ⟨ 8 ⟩      ☑ Tissue analyzer               │ │   40 px wider tiles) │
```
At 770 px the grid is two columns, so STRUCTURAL costs 2 rows instead of 4 and DWI 2 instead of 3 —
the whole form plus EXISTING OUTPUTS is above the fold at 900.

**Numbers this lane hits** — dead space ≤ 22 % (v2 today: **74 %**); `panes = {nav 216, content
1064, work ≥ 660, right 360}` at 1280 and `{…, content 1224, work ≥ 760, right 400}` at 1440;
`firstScreenControls(page).hidden` empty at 1280 × 800; status cells `lastJob`, `planCost`.

---

## 3. Simulator — shape A

### 1280 × 800

```
│ nav  │ work pane                                     666 │┃│ run panel                          360 │
├──────┼───────────────────────────────────────────────────┼─┼─────────────────────────────────────────┤
│ ⚡ ►  │ SOURCE ⟨ Montage │ Flex result │ Free-hand ⟩      │ │ PLAN                                 ⟳ │
│      │ Net ⟨GSN-HydroCel-185 ⌄⟩  ⟨Uni-polar ⌄⟩ + New     │ │ ┌──────┬──────┬───────┬──────┐         │
│      │ ─────────────────────────────────────────────────│ │ │ JOBS │ CPUS │  MEM  │ WAITS│         │
│      │ ☑ F3_F4            E24→E124   1.0  1.0 mA  ✎ 🗑  │ │ │   2  │   8  │ 16 GB │   0  │         │
│      │ ☐ Thalamus_target  E37→E87      —          ✎ 🗑  │ │ └──────┴──────┴───────┴──────┘         │
│      │ ☑ L_Insula_target  E37→E18   1.0  1.0 mA  ✎ 🗑  │ │           Thalamus   L_Insula          │ 24
│      │ ☐ E2E_Test_Montage E1→E2,E3→E4  —          ✎ 🗑  │ │ ernie       new        new             │ 24
│      │ (8 rows visible; the table scrolls in place)      │ │ 101      overwrite      ·              │ 24
│      │ ─────────────────────────────────────────────────│ │ new · skip · overwrite · blocked · wait│
│      │ ▾ RUN NAME       Thalamus                        │ │ ⚠ Overwrites ernie/Simulations/Thalamus│
│      │ ▸ ELECTRODES     ellipse · 8×8 mm · gel 4 mm   • │ ├─────────────────────────────────────────┤
│      │ ▸ CONDUCTIVITY   isotropic · SimNIBS defaults    │ │ TERMINAL  sim·ernie·succeeded 12m  ⌕⇩⧉│
│      │ ▸ OUTPUT FIELDS  TI_max                          │ │ 11:52:40 INFO  simnibs: solving …      │
├──────┼───────────────────────────────────────────────────┤ │ 11:58:02 INFO  wrote TI_max.nii.gz     │
│      │ 2 jobs · 8 CPU · 16 GB · 1 overwrite              │ │ 11:58:03 INFO  done in 5m22s           │
│      │                       [ Run 2 simulations  ⌘⏎ ]  │ │                                        │
```

The stage columns here are the **montages** of the run — the matrix is `subject × montage` for
`kind = "sim"`, which is what `POST /api/plan/sim` returns one `PlanJob` per.

**Empty state** — no montage ticked: the plan is idle, the digest reads *"Select at least one
montage."* and the primary is disabled **with that string as its tooltip** (never a silent disabled
button). The matrix area shows the two-line select-a-subject block.

### 1440 × 900

```
│ nav  │ work pane                                                      770 │┃│ run panel        400 │
```
Two-up: RUN NAME and ELECTRODES share a row; the montage table shows 12 rows.

**Numbers** — dead space ≤ 22 % (v2 today: **67 %**); panes as Pre-processing; `hidden` empty.

---

## 4. Optimizer — shape A, Method segment (U7: one page, was two)

### 1280 × 800 — Flex

```
│ nav  │ work pane                                     666 │┃│ run panel                          360 │
├──────┼───────────────────────────────────────────────────┼─┼─────────────────────────────────────────┤
│ ◎ ►  │ METHOD ⟨ Flex │ Ex │ mEx ⟩       Run name ⟨NewRun⟩│ │ PLAN                                 ⟳ │ 28  ← the merge
│      │ ─────────────────────────────────────────────────│ │ ┌──────┬──────┬───────┬──────┐         │
│      │ ▾ TARGET                                          │ │ │ JOBS │ CPUS │  MEM  │ WAITS│         │
│      │   Region ⟨Cortical│Subcortical│Spherical⟩         │ │ │   1  │   8  │ 12 GB │   0  │         │
│      │   Space  ⟨Subject│MNI⟩   Atlas ⟨DK40 ⌄⟩ ⓘ        │ │ └──────┴──────┴───────┴──────┘         │
│      │   Regions [L·bankssts ×] [+ add]                  │ │            flex-search                 │ 24
│      │   x 10.0  y −20.0  z 15.0  r 8.0 mm      🗑 +     │ │ ernie          new                     │ 24
│      │ ▾ OBJECTIVE                                       │ │ new · skip · overwrite · blocked · wait│
│      │   Goal ⟨focality — threshold-free ⌄⟩ ⓘ            │ ├─────────────────────────────────────────┤
│      │   Post-proc ⟨max_TI ⌄⟩  Non-ROI ⟨everything ⌄⟩    │ │ TERMINAL  No run yet for this page.    │
│      │ ▸ ELECTRODES  4 × ellipse 8×8 · min dist 20 mm  • │ │ Optimizer jobs appear here.            │     empty state
│      │ ▸ SOLVER      DE · pop 13 · maxiter 500 · tol 0.1 │ │                                        │
│      │ ▸ POST-RUN    simulate the best montage: off      │ │                                        │
├──────┼───────────────────────────────────────────────────┤ │                                        │
│      │ 1 job · 8 CPU · 12 GB                             │ │                                        │
│      │                        [ Run flex search   ⌘⏎ ]  │ │                                        │
```

**Where Ex / mEx differ** — the skeleton is identical; three things change and nothing else:

1. a **precondition strip** appears directly under the Method segment, 28 px, replacing the v2
   "Subject and leadfield" card: `Leadfield · GSN-HydroCel-185 ✓ 2.0 GB`, or, when it is missing,
   `⚠ No leadfield for GSN-HydroCel-185 — required.  [Generate (≈40 min)]`. A hard prerequisite is a
   gate, not a form field, and it is `blocked` in the plan matrix while it is unmet;
2. **ELECTRODES** becomes the four bucket comboboxes (`ElectrodeBuckets`), and **SOLVER** is not
   rendered — an exhaustive search has no solver;
3. the stats strip grows a fifth tile, **COMBOS** (`185 electrodes · 7 splits · 119 140`), because
   the cost of widening a bucket must be visible *while* you widen it. mEx adds `TRIPLETS`.

The ROI picker is one shared `RoiPicker` across all three methods.

### 1440 × 900

```
│ nav  │ work pane                                                      770 │┃│ run panel        400 │
```
TARGET goes two-up (Region+Space on one row, Atlas+Regions on the next), so OBJECTIVE clears the
fold and all three disclosures are visible at 900 without scrolling.

**Numbers** — dead space ≤ 22 %; `panes` as Pre-processing; `hidden` empty (Tier 1 = Method, Region,
Space, Atlas/coords, Goal — five controls).

---

## 5. Analyzer — shape A

### 1280 × 800

```
│ nav  │ work pane                                     666 │┃│ run panel                          360 │
├──────┼───────────────────────────────────────────────────┼─┼─────────────────────────────────────────┤
│ ▦ ►  │ SCOPE ⟨ Subject │ Group │ Figures ⟩               │ │ PLAN                                 ⟳ │ 28
│      │ Simulation ⟨Thalamus ⌄⟩   TI_max · mesh + voxel   │ │ ┌──────┬──────┬───────┬──────┐         │
│      │ ─────────────────────────────────────────────────│ │ │ JOBS │ CPUS │  MEM  │ WAITS│         │
│      │ ▾ SPACE                                           │ │ │   1  │   4  │  8 GB │   0  │         │
│      │   Space ⟨Mesh│Voxel⟩   Tissue ⟨Grey matter ⌄⟩     │ │ └──────┴──────┴───────┴──────┘         │
│      │   Field ⟨Auto (TI_max / mTI_max) ⌄⟩               │ │           Sphere_10                    │
│      │ ▾ TARGET                                          │ │ ernie        skip                      │
│      │   Region ⟨Cortical│Subcortical│Spherical⟩         │ │ new · skip · overwrite · blocked · wait│
│      │   Atlas ⟨DK40 ⌄⟩                                  │ │ ⚠ An analysis named Sphere_10 exists   │
│      │   Regions [superiorfrontal ×] [precentral ×]      │ │   and will be kept. Rename to re-run.  │
│      │ ▸ OUTPUT   CSV + PDF report, named Sphere_10      │ ├─────────────────────────────────────────┤
│      │ ▸ ADVANCED                                        │ │ TERMINAL  analyzer·ernie·failed 9s ⌕⇩⧉│
├──────┼───────────────────────────────────────────────────┤ │ 09:31:02 INFO  loading TI_max.nii.gz   │
│      │ 1 job · 4 CPU · 8 GB · 1 skip                     │ │ 09:31:09 ERROR no ROI nodes in mask    │     --danger ink
│      │                        [ Run analysis      ⌘⏎ ]  │ │ 09:31:09 INFO  exit 1                  │
```

`Group` swaps the top row for a subject multi-select and the matrix gains one row per subject;
`Figures` swaps the form for the nilearn/cluster panels and the run panel is unchanged.

**Empty state** — no simulation chosen: idle plan, digest = *"Pick a simulation to analyze."*

### 1440 × 900 — SPACE and TARGET go two-up; every disclosure fits above the fold.

**Numbers** — dead space ≤ 25 %; panes as Pre-processing; `hidden` empty.

---

## 6. Results — shape B, three columns (U4: subject-centric, no dropdown)

### 1280 × 800

```
│ nav  │ subjects  200 │ outputs tree              438 │ preview                              426 │
├──────┼───────────────┼─────────────────────────────────┼────────────────────────────────────────────┤
│ ▥ ►  │ ⌕ Filter…     │ ⌕ Filter outputs…   ⟨All│Sim│  │ Thalamus simulation report            ⧉ ⤓ │ 28
│      │ ─────────────│  Flex│Ex│Analysis│Report⟩       │ ────────────────────────────────────────── │
│      │ ernie      11 │ ─────────────────────────────── │                                            │
│      │ 101         1 │ ▾ Simulations                 3 │  sub-ernie — Thalamus simulation           │
│      │ MNI152      0 │   ▪ Thalamus     TI  mTI      › │                                            │
│      │ ───────────── │   ▪ L_Insula     TI           › │  Montage F3_F4 · 2.0 mA · isotropic        │
│      │ Group       2 │   ▪ docs_example      mTI     › │  ┌───────────┬─────────┬──────────┐        │     report iframe
│      │               │ ▾ Flex runs                   1 │  │ Field     │ Max V/m │ Mean ROI │        │
│      │               │   ▪ flex_Thalamus_20260810    › │  │ TI_max    │   0.981 │    0.412 │        │
│      │               │ ▾ Ex / mEx runs               1 │  │ TI_normal │   0.774 │    0.301 │        │
│      │               │   ▪ ex_L_Insula_20260812      › │  └───────────┴─────────┴──────────┘        │
│      │               │ ▾ Analyses                    2 │                                            │
│      │               │   ▪ Thalamus / Sphere_10      › │                                            │
│      │               │   ▪ L_Insula / DK40_L         › │ ────────────────────────────────────────── │
│      │               │ ▾ Reports                     3 │ ARTIFACTS  report.html · summary.csv ·     │
│      │               │   ▪ Thalamus report  1 Aug    › │            TI_max.nii.gz · convergence.png │
│      │               │                                 │ [Open in viewer] [Reveal] [Open externally]│ 28
```

Column widths: **200 / flex / 40 % of the content box (floor 380, ceiling 560)**. Type badges (`TI`,
`mTI`, `flex`, `ex`, `analysis`, `report`) are `Chip`s from the shared vocabulary; the counts on the
subject list are total outputs. The **Group** pseudo-subject is pinned under a rule at the bottom of
the list and holds the group catalog.

**Empty states** — a subject with nothing: the tree shows one inline line, *"ernie has no outputs
yet."* + ghost `Run a simulation`, and the **preview pane is not rendered** (the tree takes its
width). No selection in the tree: the preview shows a two-line inline empty state, not a spinner.

### 1440 × 900

```
│ nav  │ subjects  200 │ outputs tree                          534 │ preview                     490 │
```
The tree gains a `CREATED` column (relative time, right-aligned) at 534 px.

**Numbers** — dead space ≤ 20 % (v2 today: **86 %**); `panes = {list 200, tree ≥ 400, preview
426 ± 8}` at 1280 and `{200, ≥ 490, 490 ± 8}` at 1440; status cell
`counts = "ernie · 3 simulations · 2 analyses · 1 report"`; **no page header, no subject dropdown**
(both present in the v2 build).

---

## 7. Viewer — shape C, the embed (U5: the inspector is gone)

### 1280 × 800

```
┌──────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  TI  │ example ⌄ › ernie ⌄                                              ⌕ ⌘K  ● connected     0 running               │ 40
├──────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▣    │ SUBJECT ⟨ernie ⌄⟩  SIMULATION ⟨Thalamus ⌄⟩  FIELD ⟨TI_max ⌄⟩  SPACE ⟨Subject│MNI⟩                        ⟳    │ 40  source bar
│ ▤    ├────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ⚡    │                                                                                                                │
│ ◎    │                                                                                                                │
│ ▦    │                        < i f r a m e   s r c = " / t e t r a v o x / " >                                       │
│ ▥    │                                                                                                                │
│ 👁 ►  │                        1 2 2 4   ×   6 6 4      (the embed owns every control inside)                          │ fills
│ ☰    │                                                                                                                │
│ ⚙ ?  │                                                                                                                │
├──────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ No jobs running                                                                                                    ⌃ │ 32
├───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ RAS  12.0  −18.0  9.0 │ Space subject │ Renderer Apple M2 Pro           ● connected │ tit 3.0.0 · api v1              │ 24
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The rail is **56 px icons on this page at every width** — that is what buys the embed ≥ 1200 px at
1280, below which the embed collapses its own panels and the page becomes a picture with no
controls. It is the only page allowed to force it.

**The three non-embed states**, each a centred block `max-width: 480px` over `--canvas`, no
inspector to fall back on:

```
   no-webgl2                         no-embed                          not bundled
   ─────────────────────────         ─────────────────────────         ─────────────────────────
   This computer has no WebGL2.      The viewer did not answer.        This server has no viewer
   Detected renderer: SwiftShader.   Nothing replied to the            bundle.
   Chromium M137 removed the         handshake in 8 seconds.           The image was built without
   software fallback, so there                                         the Tetravox embed.
   is nothing to switch on.          [ Reload viewer ]
   (no buttons)                                                        (no buttons, no source bar)
   status: Renderer "no WebGL2"      status: no Renderer cell          status: no Renderer cell
```

### 1440 × 900 — identical bands; the embed is **1384 × 764**.

**Numbers** — dead space ≤ 12 % (a canvas counts as content; v2 today: **16 %** — the one page
already close); `panes = {nav 56, content 1224, work ≥ 1200 × ≥ 640, right 0}`; status cells
exactly `ras`, `space`, `renderer` and nothing else.

---

## 8. Jobs — shape B, two-pane

### 1280 × 800 — with history, a job selected

```
│ nav  │ work pane                                                704 │ detail                        360 │
├──────┼────────────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ ☰ ►  │ ⟨All states ⌄⟩ ⟨All kinds ⌄⟩ ⟨All subjects ⌄⟩ ⟨Jobs│Groups⟩   │ #14  sim · ernie · running        │ 28  filters
│      │ ─────────────────────────────────────────────────────────── │ ───────────────────────────────── │ 28  header
│      │ STATE     KIND SUBJECTS STAGE   ELAPSED  CPU  RSS  WAITING  │ Started    12:04:01               │
│      │ ● running sim  ernie    active     4m12s  780%  9.1G   —    │ CPUs / mem 8 · 16 GB              │ 28  rows
│      │ ● queued  pre  101      —            0s    —     —   #14    │ Output     …/Simulations/Thalamus │
│      │ ✓ ok      pre  ernie    done      18m02s  640%  6.2G   —    │ ───────────────────────────────── │
│      │ ✗ failed  anal ernie    roi         0m09s   —     —   —     │ CONSOLE  ⌕ Filter…      ⇩ follow ⧉│ 24
│      │ ✓ ok      flex ernie    done      41m10s  790% 11.4G   —    │ 12:04:01 INFO  simnibs: solving   │
│      │ (24 rows fit at 800; history included — the table is the     │ 12:04:09 INFO  step 2/9           │     fills
│      │  page, not a live-only list)                                 │ 12:04:11 WARN  slow assembly      │
│      │                                                              │ ───────────────────────────────── │
│      │                                                              │ [Stop job]        [Reveal log]    │ 28
```

**Empty state** — no job selected: the detail pane is **not rendered** and the table is 1064 px
wide. No jobs at all: one centred `EmptyState` ("Nothing has run yet."), one ghost action
(`Open Pre-processing`), and no filter strip.

### 1440 × 900

```
│ nav  │ work pane                                                                    864 │ detail      360 │
```
The table gains `STARTED` and `GROUP` columns at 864 px; 30 rows fit at 900.

**Numbers** — dead space ≤ 25 % with history, ≤ 30 % empty (v2 today: **92 %** — the worst page in
the build); `panes.right` is `360` or **`0`**, never a pane holding "Select a job to see its
detail"; status cell `jobCounts = "1 running · 3 queued · 1 failed"` **and no RAS / Space /
Renderer** (the v2 bug U8 exists to kill).

---

## 9. What every frame owes the metric

| page | dead space @1280 | `panes` @1280 | first-screen Tier 1 |
|---|---|---|---|
| subjects | ≤ 25 % / ≤ 30 % unselected | 216 · ≥ 704 · 360 or 0 | n/a |
| preprocess | ≤ 22 % | 216 · ≥ 660 · 360 | `hidden` empty |
| simulator | ≤ 22 % | 216 · ≥ 660 · 360 | `hidden` empty |
| optimizer | ≤ 22 % | 216 · ≥ 660 · 360 | `hidden` empty |
| analyzer | ≤ 25 % | 216 · ≥ 660 · 360 | `hidden` empty |
| results | ≤ 20 % | 200 / ≥ 400 / 426 ± 8 | n/a |
| viewer | ≤ 12 % | 56 · ≥ 1200 × ≥ 640 · 0 | n/a |
| jobs | ≤ 25 % / ≤ 30 % empty | 216 · ≥ 704 · 360 or 0 | n/a |

At 1440 × 900 the same limits hold with `content = 1224`, run panels at `400`, work panes at
`≥ 760`, the Results preview at `490 ± 8` and the Viewer embed at `≥ 1360 × ≥ 740`.

# Results — parity checklist

There is no single "Results tab" in the PyQt GUI — this screen consolidates the results-facing
parts of `analyzer_tab.py`, `flex_search_tab.py`, `ex_search_tab.py` and the standalone HTML
reports those tabs open externally, into one browsable, per-subject tree (task spec, P6 lane).

## Sections

| Qt source | v3 equivalent | Status |
|---|---|---|
| Simulator/report generation opens the HTML report in the OS browser | "Simulations" tab: report shown inline in a sandboxed `<iframe sandbox="allow-scripts">` served by `GET /api/files/report/{id}`, with a picker when a simulation has more than one report | Done |
| (implicit — montage images live inside the generated report) | Not browsed separately; the report iframe already contains them (the reports are self-contained HTML with inline/base64 images, consistent with the report's own CSP: `img-src data: blob:`) | Done via the report, see gap below |
| Simulation output files (mesh/NIfTI), opened manually via Finder/Explorer | "Artifacts" card: `ArtifactList` over `SimulationDetail.niftis`/`.meshes`, each row "Open" (**opens this simulation in the embedded viewer** — an in-app deep link to `/viewer?kind=simulation&subject=&simulation=`, not a launch) + "Reveal" | Done — changed in v3, see the note below |
| `flex_search_tab.py` results: manifest.json fields shown after a run finishes | "Flex runs" tab: run list + a `DefinitionList` of the manifest's fields (goal, ROI, created, and every `manifest` key) + an "Artifacts" card | Done |
| Flex-search plot PNGs (Pareto front, convergence) referenced in the run folder | `FlexRun.artifacts` → the same "Artifacts" card (`ArtifactList`, "Open" via `GET /api/files/artifact?path=`) | Done |
| `ex_search_tab.py` / mEx results table (`final_output.csv`) | "Ex / mEx runs" tab: run list (best montage/score) → full results `DataTable` from `GET /api/catalog/ex-runs/{run}/results` + an "Artifacts" card from `ExRun.artifacts` | Done |
| `analyzer_tab.py` results: summary stats + PDF report per analysis | "Analyses" tab: simulation picker → analysis list → summary `DataTable` (`GET /api/catalog/analyses/{name}/summary`) + PDF `<embed>` (`GET /api/files/artifact?path=`) + "Open in viewer" (`?kind=analysis`) | Done — changed in v3, see the note below |
| Group comparison / nilearn visuals / group analyses (spread across several tabs + the Nilearn Visuals panel) | "Group" tab: three generic tables from `GET /api/catalog/group` (`stats`, `nilearn`, `group_analyses`) | Simplified — see gap below |
| "Reveal in Finder/Explorer" (implicit OS behaviour) | `Reveal` button wired to `TitBridge.showItemInFolder` | Done |

## v3: no external viewers (D3)

X11 is out of the runtime and `POST /api/viewers/{freeview,gmsh}` is out of the server
(`docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` D3), so **every "Open" on this page is now an in-app
navigation to the Viewer**, which loads the scene into the embedded Tetravox viewer. `launchFreeview`,
`launchGmsh` and the `GET /api/view/custom` fetch that fed them are deleted from `api.ts`, and the
"Open externally ▾" menu the UX plan sketched (§2) never ships: there is nothing external to open.

One consequence worth stating plainly: a row's "Open" is scoped to the **simulation or analysis**,
not to the individual file the row names — the server builds a scene per (subject, simulation,
field), and there is no `GET /api/view` shape that means "just this one NIfTI as a layer on the T1"
short of `kind=custom` with a `path`, which loses the base layer. Opening one arbitrary artifact on
its own is gap 5 below.

## Known gaps (report to orchestrator)

1. ~~**No catalog listing for a simulation's montage/plot PNGs.**~~ **Partially resolved** —
   `FlexRun`/`ExRun` now carry `artifacts` (CHANGES.md fix:contract item 6, populated
   server-side by fix:backend-catalog item 2's `tit.catalog._dir_artifacts`), so the "Flex runs" /
   "Ex / mEx runs" tabs now browse each run's PNGs/CSVs/manifests via their own "Artifacts" card.
   `SimulationDetail` still has no separate `images: [{path, label}]` field for a simulation's own
   montage diagrams independently of the report that already embeds them — `niftis`/`meshes` cover
   the mesh/NIfTI outputs, not standalone plot PNGs, so that half of the original gap stands.
2. ~~**`window.tit` has no `showItemInFolder` (or any reveal) method yet.**~~ **Resolved** — P9's
   bridge implements it (host<->container mapping via `stack.getCurrent()`'s mount, or
   `GET /api/project`'s `host_path` as a fallback when this app did not itself start the stack);
   `reveal()` calls it directly.
3. **Group tables are rendered generically.** `GroupCatalog.stats/nilearn/group_analyses` are
   typed `additionalProperties: true` (deliberately, per the contract) — this page infers columns
   from the union of keys it sees rather than hard-coding a shape, so it stays correct as the real
   `tit.catalog` group-catalog builder's fields evolve, but it also means no field gets special
   rendering (e.g. a nilearn PNG thumbnail, a "created" date formatted). Low priority; flagged here
   rather than guessing at a shape the contract explicitly left open.
4. **Ex/mEx run list vs. results table naming.** Per `docs/dev/HISTORY.md § 2026-08-27 (v3 build program)` §3 (B backend
   budget), the ex-search run-name/directory-naming convention "settle with a real run in Phase 2"
   is still open; this page trusts `ExRun.run_name` and `.path` as given by the catalog and doesn't
   re-derive either.

5. **"Open" is per-simulation, not per-artifact.** See the v3 note above: a single NIfTI or mesh row
   navigates to the whole simulation's scene rather than to itself. Closing it needs either a
   `GET /api/view/custom?path=&subject=` that keeps the subject's T1 as a base layer, or a way for
   the Viewer page to merge a custom layer into a built scene — server work, not page work.

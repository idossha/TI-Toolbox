# Tetravox 0.3.11 intake, self-updating embed, dot electrodes, one selection grammar (plan of record, 2026-09-05)

Asked (verbatim intent): ship the new Tetravox (0.3.10/0.3.11 visualisation fixes) into TI-Toolbox; make the
toolbox pick up future Tetravox releases **without a TI-Toolbox release**; draw EEG electrodes as dots whose
**colour** carries idle/selected/disabled (no rings); test select/deselect of electrodes and channels; and one
selection logic for every page, modelled on the 2.5.0 simulator (job cards + one pick list), because the current
v3 flow is too convoluted to see which jobs you are about to run.

## 0. What is true today (measured 2026-09-05)

| Fact | Where |
|---|---|
| Tetravox `origin/main` = **0.3.11** (`fix(render): surface opacity`, `fix(ui): view controls`); releases 0.3.7–0.3.11 exist on GitHub, **none carries an embed tarball**. | `gh release view v0.3.11` |
| `packages/embed` (0.4.0, protocol 2) exists only on local `feat/embed-protocol2` (5 ahead, **11 behind** main). Its `release.yml` already builds + uploads `tetravox-embed-<v>.tgz`. | tetravox `git log main..feat/embed-protocol2` |
| TI-Toolbox already has the whole dynamic-delivery machinery: `tit/tetravox/{install,store,protocol}.py`, `GET/POST /api/tetravox[/updates|/install|/activate]`, Settings UI, protocol **range** pin (E1) and verified explicit install (E3). | `tit/server/routes/tetravox.py` |
| Its default release index is `raw.githubusercontent.com/idossha/tetravox/main/packages/embed/releases.json` — **that file does not exist on any branch**. So "check for updates" can never find anything. | `tit/tetravox/install.py:70` |
| Electrodes are already a protocol-2 points layer, `shape: "sphere"`, amber `stateColors.selected`, grey `disabled`. Protocol offers `shape: "dot"` (constant screen size). | `desktop/src/renderer/pages/_shared/scene/embedScene.ts:200` |
| No test exercises electrode select/deselect end-to-end. | `desktop/tests/` |
| 2.5.0 simulator: **job cards** (subject / source / net / U-M / currents) with a per-card `n selected` badge, and **one** `ExtendedSelection` pick list that shows the focused card's candidates; selection is saved per card; Select-all / Clear. | `git show v2.5.0:tit/gui/simulator_tab.py` 180–760 |
| v3 simulator: SubjectsField (mode grammar, `_shared/subjects/model.ts`) × three tabs (Montage/Flex/Freehand) each pushing `SelectedRow`s; optimizer/analyzer each have their own shape. | `desktop/src/renderer/pages/simulator/index.tsx` |

## 1. Decisions

| # | Decision | Prevents |
|---|---|---|
| T1 | **The embed ships with every Tetravox release.** `feat/embed-protocol2` is rebased onto main (so the bundle carries 0.3.10/0.3.11 fixes) and merged; `release.yml` uploads `tetravox-embed-<v>.tgz` **and** rewrites `packages/embed/releases.json` (append `{version, protocol, url, sha256, published, notes}`) in the same release commit. The index is generated, never hand-edited. | An index that drifts from the assets, and a release with no bundle. |
| U1 | **TI-Toolbox self-updates the viewer, within its protocol range, without a toolbox release.** On server start (and every 24 h while running) `tit.tetravox` fetches the index, picks the newest entry whose `protocol` is inside `supported_range()`, and installs it in a background thread; the new bundle activates on the **next embed mount**, never under a live frame. Settings gets `Auto-update viewer` (default on, env `TIT_TETRAVOX_AUTO_UPDATE=0` for operators), the current/available versions, and the existing roll-back. Offline is silent. Install keeps E3 (sha256 before unpack, traversal-safe, allowlisted hosts). | A viewer that never moves, and a viewer that moves to a protocol the host cannot speak. |
| U2 | The **baked floor** (`/opt/tetravox/embed`) is bumped to the first embed published under T1 at the next TI-Toolbox release; that is the only Tetravox-related edit a toolbox release ever needs, and it is optional. | Tetravox releases forcing toolbox releases. |
| E1 | **Electrodes are screen-space dots; state is colour, nothing else.** `shape: "dot"`, one fixed pixel radius; `stateColors` = idle (marker colour), selected (accent), disabled (muted grey); the point-tool selection ring is never armed on electrode panes. Channels (pairs) colour their two electrodes with the pair's colour. | Rings and spheres that scale with zoom and hide the scalp. |
| E2 | **Select/deselect is a pure reducer with tests at two levels.** Unit: toggle, second click deselects, disabled cannot be selected, pair completion, clear. Offscreen Playwright against the embed: click an electrode → pixel at its projected position turns the selected colour; click again → idle colour; a disabled electrode stays grey. | "It looked right in the demo." |
| S1 | **One selection grammar, taken from 2.5.0.** Every job-taking page (Simulator, Optimizer flex/ex, Analyzer) is `job cards + one pick list + one plan line`. A card is the thing that varies per job group (subject set, source, net, mode); the pick list shows the focused card's candidates with click-toggle, shift-range, Select all, Clear and a `n selected` badge on the card; the plan line states the job count as a sentence (`3 subjects × 2 montages = 6 jobs`). The selection algebra lives once in `_shared/selection/` (generalised from `_shared/subjects/model.ts`) and is what electrodes, subjects, montages, regions and jobs all use. | Three pages with three ways to pick, and a run whose job count is a surprise. |
| S2 | UI/UX may change beyond the pick list where it simplifies (fewer tabs, collapsed advanced parameters), but the wording rules already in force stay (summary line, blocked sentence, one job per subject note). | Redesign for its own sake. |

## 2. Lanes (in flight 2026-09-05; T in the Tetravox repo, U/E/S in this worktree on disjoint files)

- **T — Tetravox embed release** (repo `~/00_development/tetravox`): rebase `feat/embed-protocol2` onto `origin/main`, generate `releases.json` in CI, seed it, open a PR. No tag; the maintainer cuts 0.3.12.
- **U — self-updating embed** (`tit/tetravox/`, `tit/server/routes/tetravox.py`, `tit/server/schemas.py`, `desktop/src/renderer/pages/settings/`): U1/U2 with tests against a loopback index.
- **E — dot electrodes + tests** (`desktop/src/renderer/pages/_shared/scene/`, run-page electrode panes, `desktop/tests/unit/electrode-*.test.ts`, `desktop/tests/e2e/electrodes.spec.ts`): E1/E2.
- **S — selection grammar** (`desktop/src/renderer/pages/_shared/selection/`, `_shared/subjects/`, `pages/simulator/`, `pages/optimizer/`, `pages/analyzer/`, their PARITY.md, tests): S1/S2.

Gate for U/E/S: `npm run typecheck && npm run lint && npm test && npm run e2e:quiet` in `desktop/`, plus `pytest tests/` for U. Nothing is committed by a lane; the maintainer reviews the diff in this worktree.

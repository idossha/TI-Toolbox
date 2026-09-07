# NB — Notebooks

*2026-09-06. Branch `feature/v3-electron-gui`. Records of record: ARCHITECTURE §7.6,
DECISIONS 2026-09-06 (NB lane), DESIGN §9 / §9.3, ROADMAP, contracts/SCHEMA-CHANGES.md.*

## The ask

> "In the left menu bar introduce a Jupyter-like environment similar to what we did in the SUNA
> project, where the TI-Toolbox environment is automatically loaded and users can run Jupyter
> notebooks from within TI-Toolbox itself."

## What was built

A **Notebooks** rail entry after Pipeline, a page at `pages/notebooks/`, and the server behind it.

| Piece | Where |
|---|---|
| Kernel registry (`jupyter_client`, cap 2, 30 min idle reap) | `tit/server/kernels.py` |
| Notebook file IO (`nbformat` v4, one directory, atomic write) | `tit/server/notebooks.py` |
| `GET/POST /api/notebooks`, `GET/PUT/DELETE /api/notebooks/{name}` | `tit/server/routes/notebooks.py` |
| `GET/POST /api/kernels`, `DELETE`/`interrupt`/`restart`, `WS /ws/kernels/{id}` | `tit/server/routes/kernels.py` |
| Response models | `tit/server/schemas.py` (`Notebook*`, `Kernel*`) |
| Contract + generated types | `contracts/openapi.v1.yaml`/`.json`, `desktop/src/renderer/api/schema.d.ts` |
| Mock server routes + a fake kernel | `desktop/tests/mock-server/server.mjs` |
| Page, session store, cells, outputs, mime, ANSI, markdown | `desktop/src/renderer/pages/notebooks/` |

Notebooks live in `<project>/code/ti-toolbox/notebooks/` — a new directory, chosen as the sibling of
the existing `code/ti-toolbox/pipelines/`, and the place the pipeline canvas's export should land
(ROADMAP item 5; `POST /api/notebooks` already accepts a document, so that is one button on the
canvas).

## What came from SUNA, and what changed

Ported, GPL-3.0, same author, attributed in each file header:

| SUNA | Here | Change |
|---|---|---|
| `python/suna_kernel/bridge.py` | `tit/server/kernels.py` | **Topology.** SUNA spawns a child process because its kernel is on the user's laptop; here the kernel runs in the container and the server is already there, so `KernelManager` is driven in-process and the stdio pipe becomes a WebSocket. Every `no-jupyter-client` / interpreter-picker / "offer to install ipykernel" branch **disappears** — there is one interpreter and it is the one every job already uses. |
| `notebook/mime.ts`, `mime.test.ts` | same names | Unchanged, except that an interactive mime falls back to its static image (no privileged output scheme here — DECISIONS). |
| `notebook/ansi.ts`, `ansi.test.ts` | same names | Unchanged; the sixteen classes map to this app's tokens. |
| `notebook/Outputs.tsx` | same name | Markdown through this page's own small renderer; `script-html` renders as inert HTML rather than in a frame. |
| `notebook/CellView.tsx` | same name | **CodeMirror → auto-sizing `<textarea>`.** No new dependency was added for this feature. |
| `notebook/session.ts` | same name | IPC channels → `/api/kernels` + `/ws/kernels/{id}`; keyed by notebook name rather than absolute path; autosave added. |
| `notebook/NotebookTab.tsx` | `index.tsx` | Modal editing and the command-mode keymap are SUNA's, verbatim in behaviour; the notebook list pane is new (SUNA opens notebooks from a file explorer this app does not have). |
| `@suna/notebook` (the model) | `notebook.ts` | Only the model half. SUNA reimplements nbformat's serializer in TypeScript because its renderer writes the file; here `nbformat` does it server-side, so the rule that survives is "unknown keys are never dropped". |

## Two defects this work found

1. **A reply could overtake the output it concludes.** A request ends on two channels — the shell
   `execute_reply` and the iopub `status: idle` — polled by two threads. Emitting the reply from the
   shell thread alone (SUNA's shape, which is fine over one serialised stdio pipe) let it reach the
   client first, and the renderer, which deletes its in-flight entry on reply, then **dropped the
   cell's output**. `KernelRegistry._finish_half` joins the halves; whichever arrives second emits.
   Found by `test_kernel_websocket_relays_a_cell` on its first run.
2. **`PathManager` has no `project_root`.** The starter cell said `pm.project_root`; the attribute
   is `pm.project_dir`. Static reading had it wrong in the server *and* in the mock; running the real
   cell against the container returned the `AttributeError` that said so.

## Commits

| | |
|---|---|
| `0dfe868c` | `feat(server): notebook kernels and .ipynb files, SUNA's bridge with the kernel inside the container` |
| `294689de` | `contract(v1): notebook and kernel paths, with the response models to match` |
| `5e0e94cd` | `test(mock): notebook files and a fake kernel that echoes print() over /ws/kernels` |
| `8a67eb76` | `feat(desktop): a Notebooks page — SUNA's notebook UI over the container's kernel` |
| `20f84e3c` | `test(notebooks): mock e2e for the whole loop, real e2e for the tit import; starter cell uses pm.project_dir` |
| (this note) | `docs(notebooks): ARCHITECTURE §7.6, DECISIONS, DESIGN §9.3, ROADMAP` |

## Gate

| Check | Result |
|---|---|
| `python3 -m pytest tests/ -q -k "kernel or notebook"` | **54 passed** — 46 new (19 kernel + 27 notebook file/route) plus the 8 pre-existing pipeline-notebook-export tests the selector also matches |
| `python3 dev/route_import_guard.py` | **23 route module(s) clean** — `kernels` 25 ms, `notebooks` 14 ms |
| `python3 dev/build_contract.py` + `dev/contracts_check.py` (v1 vs `--dump-openapi`) | **0 findings on the new paths and schemas** |
| `npm run gen:api` | regenerated; `schema.d.ts` carries the new paths |
| `npx vitest run` | **1170 passed**; `tests/unit/retained-pages.test.tsx` fails to import (`matchMedia is not a function`, uplot at module scope) — **pre-existing, another lane's**: it fails identically with `pages/notebooks/` moved out of the tree |
| `npx eslint src tests` | **0 errors** (3 pre-existing warnings) |
| `npm run typecheck` | clean for this lane; `scene/SceneCanvas.tsx(403): Cannot find name 'positionNames'` is another lane's uncommitted WIP |
| `npm run pree2e` (build) | succeeded |
| `npx playwright test notebooks.spec.ts` (offscreen, mock) | **7 passed** — create → `print(1+1)` → `2`; markdown render + double-click edit; error traceback; interrupt; save/reload round trip; list/open/delete; `b` / `dd` / `z` / `m` |
| `tests/e2e/real/notebooks.spec.ts` | **written, unrun** — see below |

`/tmp/tit-e2e.lock` was taken for the Playwright run and removed after.

## Proved live against the dev container

Before Docker Desktop stopped, `ti-toolbox-fad740e5-tit-1` was driven directly:

* `GET /api/notebooks` → `{"dir":"/mnt/000/code/ti-toolbox/notebooks","notebooks":[]}`
* `POST /api/notebooks {"name":"lane-nb-check"}` → the starter notebook, written to the project
* `POST /api/kernels` → a **real** kernel: `{"name":"simnibs","displayName":"SimNIBS + TI-Toolbox","cwd":"/mnt/000","state":"idle"}`
* `WS /ws/kernels/{id}` with `from tit import get_path_manager` → the import **succeeded** and the
  cell came back with a real IPython traceback, ANSI and all, for the wrong attribute on the next
  line. That is the load-bearing proof: `tit` is importable on that kernel with nothing installed.
* `POST /api/kernels/{id}/restart` → 200
* The server's `--reload` restart shut its kernels down, which is the lifespan hook working.

## Open

1. **The real Playwright spec has not been run.** Docker Desktop stopped on the host at 20:15
   (`~/.docker/run/docker.sock` gone, no `Docker Desktop` process) and `open -a Docker` did not bring
   it back from this session. With the container up:
   `TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> npx playwright test --project real notebooks.spec.ts`.
   The claim it adds over the direct driving above is that the *page* — not curl — runs the starter
   cell and shows `project: /mnt/…`.
2. **Jobs lost ⌘9** (DECISIONS, "Known consequence"). Ten workflow rows, nine digits. If that is the
   wrong trade, move `notebooks` to the end of `NAV_ORDER` — one line — rather than reinstating a
   `"10"` shortcut that no keyboard can send.
3. **No Dockerfile change was needed.** `nbformat` is already a hard dependency and `jupyter_client`
   arrives with `jupyterlab-lsp`/`ipykernel`. Both were verified importable under the container's
   `simnibs_python`, which is also the interpreter the server runs on. Making `jupyter_client`
   explicit in that `pip install` block would remove a transitive assumption; it was left alone
   because the Dockerfile is shared with another lane this session.
4. **ROADMAP items 1–5** (LSP completions, cell highlighting, variable explorer, interactive plots,
   the pipeline canvas's "save export here" button).

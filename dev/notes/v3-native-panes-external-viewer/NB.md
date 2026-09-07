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

## Defects this work found

Round one:

1. **A reply could overtake the output it concludes.** A request ends on two channels — the shell
   `execute_reply` and the iopub `status: idle` — polled by two threads. Emitting the reply from the
   shell thread alone (SUNA's shape, which is fine over one serialised stdio pipe) let it reach the
   client first, and the renderer, which deletes its in-flight entry on reply, then **dropped the
   cell's output**. `KernelRegistry._finish_half` joins the halves; whichever arrives second emits.
   Found by `test_kernel_websocket_relays_a_cell` on its first run.
2. **`PathManager` has no `project_root`.** The starter cell said `pm.project_root`; the attribute
   is `pm.project_dir`. Static reading had it wrong in the server *and* in the mock; running the real
   cell against the container returned the `AttributeError` that said so.

Round two — none of these were visible to a unit test, and two were invisible to the mock e2e as
well:

3. **A notebook restart aborted the whole server.** Restart closed the ZMQ channels while the iopub
   and shell pumps were still polling them. ZMQ sockets are not thread-safe, and libzmq's answer was
   `Assertion failed: pfd.revents & POLLIN (src/signaler.cpp:238)` — the `tit.server` process gone,
   every running job's API with it, because someone pressed Restart in a notebook. Pumps are now
   stopped **and joined** before any socket is touched, and the client is rebuilt (the old session
   key is stale after `restart_kernel`, which is where the preceding `Invalid Signature` came from).
   Three tests pin the ordering. **Only a real kernel could produce this.**
4. **The command-mode guard tested for a textarea.** `target.tagName === "TEXTAREA"` was true while a
   cell was a textarea and false the moment it became a CodeMirror — so typing `print(` delivered
   `r` to command mode, which re-typed the cell as **raw** and destroyed the editor mid-word.
5. **⇥ closed the completion popup it should accept.** Typing already opens it; `startCompletion`
   returns false when one is open, so ⇥ fell through to `indentWithTab` and dismissed it.
6. **A completion range that filtered every option away.** The kernel replaces the whole dotted
   expression, and CodeMirror filters options by matching the label against the replaced text — so
   a label of `subject_ids` against `catalog.subj` matched nothing and the popup never appeared.
   The range moves past the shared prefix instead.
7. **`GET /api/notebooks/examples/getting-started.ipynb` 404'd.** A plain path parameter stops at a
   separator, so the seeded example could not be opened at all. `{name:path}` now; the jail is
   `normalise_name`, and always was.
8. **The example produced no plot, and then produced two.** Without `%matplotlib inline` this
   kernel's formatter offers a Figure only as `text/plain`; with it, a trailing bare `figure` puts
   the same picture in the notebook twice.

## Round two — the maintainer ran it (2026-09-06, later)

Three reports, all reproduced and all fixed:

1. **The starter cell raised.** It called `pm.project_root`; `PathManager` has `project_dir`. It now
   imports `simnibs`, `tit.sim` and `tit.analyzer` and prints the project's real subjects, and
   `test_every_name_the_starter_cell_uses_exists` checks every name it touches against the live API
   so it cannot drift again.
2. **Markdown rendered as one flat paragraph.** The renderer now does headings, lists, emphasis,
   links, blockquotes, rules, fenced code in the mono face, GFM tables with alignment, and TeX
   through **KaTeX** — the dependency SUNA already has, bundled rather than fetched from a CDN
   (which the renderer CSP would have blocked silently).
3. **"Prove simnibs and TI-Toolbox methods are usable."** `examples/getting-started.ipynb`, seeded
   on a project's first listing: the environment, the project catalogue as a DataFrame,
   `tit.calc.get_TI_vectors`, and a real TI field off disk summarised and plotted. Run end to end
   against the container by `tests/e2e/real/notebooks.spec.ts`.

Then a fourth report — *"add python highlighting or lsp like behavior plus... autocompletion"*:

4. **Code cells are CodeMirror 6** with `lang-python`, palette from the app's own tokens.
5. **Completion is answered by the running kernel** (`complete_request` over `/ws/kernels`), not by
   a language server. `jedi 0.19.2` is already inside the container's `ipykernel`; nothing was
   added to the image.
6. **An editor settings popover** — autocompletion, signature help, brackets, line numbers, indent,
   font size, wrap — persisted per machine.

## Commits

| | |
|---|---|
| `0dfe868c` | `feat(server): notebook kernels and .ipynb files, SUNA's bridge with the kernel inside the container` |
| `294689de` | `contract(v1): notebook and kernel paths, with the response models to match` |
| `5e0e94cd` | `test(mock): notebook files and a fake kernel that echoes print() over /ws/kernels` |
| `8a67eb76` | `feat(desktop): a Notebooks page — SUNA's notebook UI over the container's kernel` |
| `20f84e3c` | `test(notebooks): mock e2e for the whole loop, real e2e for the tit import; starter cell uses pm.project_dir` |
| `8f09d153` | `docs(notebooks): ARCHITECTURE 7.6, DECISIONS, DESIGN 9.3, ROADMAP, lane note` |
| `544a3c9c` | `feat(notebooks): a real editor, kernel completion, settings, a worked example and proper markdown` |
| `a4fafab8` | `fix(notebooks): restarting a kernel aborted the server; the example produced no plot` |
| (this note) | `docs(notebooks): the editor, the kernel completer and the restart abort` |

## Gate

| Check | Result |
|---|---|
| `python3 -m pytest tests/ -q -k "kernel or notebook"` | **67 passed** |
| `python3 dev/route_import_guard.py` | **24 route module(s) clean** |
| `dev/build_contract.py` + `dev/contracts_check.py` (v1 vs `--dump-openapi`) | **0 findings** on the notebook and kernel paths |
| `npm run gen:api` | regenerated |
| `npx vitest run` | **1236 passed**; `tests/unit/retained-pages.test.tsx` fails to import (`matchMedia is not a function`, uplot at module scope) — **pre-existing, another lane's**: it fails identically with `pages/notebooks/` moved out of the tree |
| `npx eslint src tests` | **0 errors** (3 pre-existing warnings) |
| `npm run typecheck` | clean |
| `npm run pree2e` (build) | succeeded |
| `npx playwright test notebooks.spec.ts` (offscreen, mock) | **13 passed** |
| `npx playwright test --project=real notebooks` (offscreen, dev container) | **6 passed** |

The mock suite covers: create → `print(1+1)` → `2`; markdown rendered (h1, bold, code) and edited on
double-click; the example's headings, `<h2>`, ordered list, link, KaTeX display **and** inline maths
(asserting the laid-out height, not just the class), a mono-face fenced block and a right-aligned
table cell; an error traceback; interrupt; save/reload round trip; list/open/delete with the example
sorted last; `b` / `dd` / `z` / `m`; **Python highlighting** (more than two computed colours in one
cell, and no textarea left); **completion from the kernel** on typing and ⇥; a **dotted** completion
showing the member and inserting the path; **settings** applied live and surviving a reload; and
autocompletion **off** stopping the round trip.

The real suite covers: the starter cell running green and printing the real project, SimNIBS version
and subjects; the worked example running all four cells with a **matplotlib PNG** (asserted decoded,
`naturalWidth > 200`) and **two DataFrame tables**; restart resetting the execution count to `[1]`;
`from tit import get_pa` **completed by the real kernel** to `get_path_manager` and then running
without error; Python highlighted; and deleting a notebook taking its own kernel with it.

`/tmp/tit-e2e.lock` was taken for every Playwright run and removed after.

## Proved live against the dev container

`ti-toolbox-fad740e5-tit-1`, project `/mnt/000` (subjects `101`, `ernie`, `MNI152`):

* The starter cell, run under the container's `simnibs_python`:
  `project  /mnt/000` · `simnibs  4.6.0` · `subjects ['101', 'ernie', 'MNI152']` and each subject's
  simulations (`ernie: ['BU_eg1', 'L_Insula', 'Thalamus', 'pc-real-99628']`).
* The worked example, through the page: a `pandas` DataFrame as a real HTML table, the
  `tit.calc.get_TI_vectors` envelope table, `3,668,232 non-zero voxels   mean 0.1019   p99 1.1612 V/m`
  off `L_Insula_TI_MNI_MNI_TI_max.nii.gz`, and a 900×340 matplotlib figure inline as PNG.
* Completion: `from tit import get_pa` + ⇥ → `get_path_manager`, answered by the kernel
  (`jedi 0.19.2` inside the image's `ipykernel`; nothing added to the Dockerfile).
* Restart, interrupt, delete, and the kernel cap — all through `/api/kernels`.

## Open

1. **Signature help is half-built.** The preference, the server round trip (`inspect_request`,
   `Session.inspect`) and its unit tests all exist; the CodeMirror tooltip that shows the reply
   while typing arguments does not. ROADMAP item 3.
2. **Jobs lost ⌘9** (DECISIONS, "Known consequence"). Ten workflow rows, nine digits. If that is the
   wrong trade, move `notebooks` to the end of `NAV_ORDER` — one line — rather than reinstating a
   `"10"` shortcut that no keyboard can send.
3. **No Dockerfile change was needed.** `nbformat` is already a hard dependency and `jupyter_client`
   arrives with `jupyterlab-lsp`/`ipykernel`. Both were verified importable under the container's
   `simnibs_python`, which is also the interpreter the server runs on. Making `jupyter_client`
   explicit in that `pip install` block would remove a transitive assumption; it was left alone
   because the Dockerfile is shared with another lane this session.
4. **New dependencies, named as the brief asked.** `katex` (SUNA depends on it too) and six
   `@codemirror/*` packages: `state`, `view`, `language`, `commands`, `autocomplete`,
   `lang-python`. Nothing was added to the container image — `jedi` and `nbformat` were already
   there, verified in the running container rather than assumed.
5. **ROADMAP items 3–6** (signature-help tooltip, variable explorer, interactive plots, the
   pipeline canvas's "save export here" button).

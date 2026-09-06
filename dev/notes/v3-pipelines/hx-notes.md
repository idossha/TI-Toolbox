# Lane HX — harness polish + runbook (2026-09-04)

Scope: `dev/notes/v3-pipelines-program.md` §7, row **HX**. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed, staged
or stashed.

Shared dev container: `ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`, token `devtoken`,
project `/Users/idohaber/datasets/000` at `/mnt/000`.

## 1. The payload-rename fix (the finding: a replayed UI payload names a fixed output)

**Root cause.** A payload lane S2 recorded is the exact body one real UI session submitted,
including whatever name it happened to give the output *at that moment* — `stats.json`'s
`analysis_name: "smoke-ui-4863"`, `analyzer.json`'s `output_dir: null` (which
`Analyzer._resolve_output_dir`, `tit/analyzer/analyzer.py`, turns into a directory name derived
deterministically from subject+simulation+space+center+radius). Replayed later — this session or
a future one — the field is still that literal value (or still derives the same path), so a
second replay of the same recorded file always targets the *first* replay's own output: the plan
reports it `exists`, and since a payload is allowed to legitimately name a real run (not a
harness bug), the row *skips* instead of running (decision P6 working as designed, on the wrong
target — S1's own notes flagged exactly this for `stats.json` and `analyzer.json`).

**Fix** (`tests/smoke/matrix.py`): a new `Row.payload_rename` field —
`(config, ctx, row) -> None`, mutating `config` in place — documented per kind directly above
the row(s) it applies to (`_rename_analyzer_payload`, `_rename_stats_payload`,
`_rename_nifti_average_payload`, `_rename_nilearn_payload`, `_rename_sim_payload`), each
rewriting exactly the field named in its docstring to `ctx.name(row.id)` (or, for `sim`,
`ctx.name(f"{row.id}-{i}")` per montage). Wired onto `analyzer_mesh`, `analyzer_voxel`,
`stats_group`, `nifti_average`, `nilearn`, `sim_ti`, `sim_mti`. `tests/smoke/test_kinds.py`'s
`load_submission` calls it on every loaded payload, before the config is used for anything.

**Deliberately not touched:**
- `flex.json`'s `output_folder: null` — `tit/opt/flex/flex.py::_run_flex_search_inner` already
  calls `generate_run_dirname` itself when it's null, so every replay gets a fresh, timestamped
  directory without this harness's help (verified by reading the code, `tit/opt/flex/flex.py`
  lines ~157-163).
- `source.json` — the forward-solution pipeline writes to one fixed `forward/` directory per
  subject; there is no name-bearing field to rewrite (S2's own notes say the same: "no run-name
  field").
- `pre.json` — currently unreachable by the loader anyway (every `pre` row has a `group_tag`,
  and the kind-level fallback explicitly excludes tagged rows, per S1's own fix).

**Unit tests** (`tests/smoke/test_harness_selftest.py`, 7 new, 2 updated): one test per rename
function proving the field is rewritten to the expected value; one proving two different
`run_id`s produce two different names from the *same* payload file (the actual failure mode);
one proving a kind with no rename rule (`flex`) is left untouched. Two pre-existing tests
(`test_loader_prefers_a_recorded_ui_payload_over_the_builtin_config`,
`test_loader_accepts_a_bare_config_object`) needed updating: `sim_ti`'s and `nilearn`'s own
payload_rename now runs on every load, so their old literal-value assertions no longer held —
updated to assert the *renamed* value instead, with a comment explaining why.

**Real proof — the affected rows replayed twice in a row**, back to back, against the shared
container (no `--smoke-keep`, i.e. cleanup ran both times):

```
TIT_SMOKE_PROJECT_HOST=/Users/idohaber/datasets/000 \
  dev/smoke.sh analyzer_mesh analyzer_voxel stats_group nifti_average nilearn sim
```

| Pass | Result | Wall | Table |
|---|---|---|---|
| 1 | **7 passed, 0 failed** | 51.7s | `tests/smoke/artifacts/results-20260904T010508Z-200417.md` |
| 2 (immediately after) | **7 passed, 0 failed** | 51.6s | `tests/smoke/artifacts/results-20260904T010609Z-200517.md` |

Every one of the five `completed` rows (`analyzer_mesh`, `analyzer_voxel`, `stats_group`,
`nifti_average`, `nilearn`) sourced `payload:` both times, with **distinct job ids** and
**distinct output names** (`smoke-200417-*` in pass 1, `smoke-200517-*` in pass 2 — the two
`run_id`s, six minutes apart) — the exact thing that used to make pass 2 skip. `sim_ti`/`sim_mti`
(`started_then_cancel`) also replayed cleanly both times on distinct montage names. Checked
`GET /api/jobs` clear before each pass. Both manifests show **every created path removed**
(`removed: true`), and `find /Users/idohaber/datasets/000 -iname "*smoke-200417*" -o -iname
"*smoke-200517*"` returned nothing after either pass.

## 2. `dev/smoke.sh` — `--list` + a copy-pasteable selector

**Added `--list`**: prints every container labelled `tit.stack=ti-toolbox-v3,tit.service=tit`
(name, port, `tit.host_project_dir`, and the exact `TIT_SMOKE_CONTAINER=<name> dev/smoke.sh` to
select it), runs nothing, exit 0 (exit 2 if none are running — the existing `die_cannot_check`
path, unchanged).

**Improved the ambiguous-container die path** to reuse the same `describe_container` helper, so
"more than one dev stack is running" now prints the *exact* selector under each container
instead of a generic "set one of these two variables" pointer.

**Bug found and fixed while testing this**: `describe_container`'s port lookup
(`... | grep -v '^$' | head -1`) exits nonzero under `pipefail` when a container publishes no
port at all (grep finds nothing to keep) — which aborted the whole script instead of printing
`port=?`. Only visible with a container that isn't a real dev stack (a throwaway fixture); the
main container-selection port lookup is unaffected (it always resolves to a real published
port and its own `[ -n "$port" ] || die_cannot_check` still gates it — `describe_container` is
diagnostic-only). Fixed with `|| true` on that one pipeline.

**Real proof**, against the live shared container plus one throwaway second container
(`docker run --label tit.stack=ti-toolbox-v3 --label tit.service=tit ...`, stopped and removed
immediately after):

```
$ dev/smoke.sh --list          # one container
smoke: 1 container(s) labelled tit.stack=ti-toolbox-v3,tit.service=tit:
  ti-toolbox-fad740e5-tit-1  port=8765  project=/Users/idohaber/datasets/000
    -> TIT_SMOKE_CONTAINER=ti-toolbox-fad740e5-tit-1 dev/smoke.sh
exit=0

$ dev/smoke.sh --list          # two containers (fixture added)
smoke: 2 container(s) labelled tit.stack=ti-toolbox-v3,tit.service=tit:
  tit-smoke-selftest-fake  port=?  project=/tmp/smoke-selftest-fake-project
    -> TIT_SMOKE_CONTAINER=tit-smoke-selftest-fake dev/smoke.sh
  ti-toolbox-fad740e5-tit-1  port=8765  project=/Users/idohaber/datasets/000
    -> TIT_SMOKE_CONTAINER=ti-toolbox-fad740e5-tit-1 dev/smoke.sh
exit=0

$ dev/smoke.sh --smoke-kinds project_init    # two containers, no selector
smoke: 2 containers labelled tit.stack=ti-toolbox-v3; pick one with the
exact selector printed under it (or TIT_SMOKE_PROJECT_HOST=<project dir>):
  <both printed as above>
smoke: cannot check -- more than one dev stack is running (dev/smoke.sh --list shows this any time)
exit=2

$ TIT_SMOKE_PROJECT_HOST=/Users/idohaber/datasets/000 dev/smoke.sh project_init   # disambiguated
smoke: container f17995acd796 -> http://127.0.0.1:8765, project /Users/idohaber/datasets/000
1 passed, 68 deselected in 1.09s
```

## 3. `dev/notes/v3-pipelines/RUNBOOK.md`

One page, commands-only, covering dev mode, Level A, Level B, the restart rule, the
one-FEM-at-a-time rule, and where the results tables live. Every command in it was run this
session except the ones it explicitly cites from another lane (D0's own `npm run dev`/full
Electron acceptance run) — never claimed as this lane's own. See the file for the exact
evidence next to each command; the two things worth flagging here:

- **Verified live, not previously documented anywhere in this program**: `npx playwright test
  --project real <spec>.spec.ts` (the exact form `dev/notes/v3-pipelines-program.md` §7's own
  CR row and this lane's own task both name) **fails** on Playwright 1.62.1 —
  `Project(s) "tests/e2e/real/nilearn-visuals.spec.ts" not found`. `--project` takes a variadic
  list in this version, so the trailing spec path is swallowed as a second project name. Fixed
  form: `--project=real` (with `=`). Real run, offscreen, quiet-checked:
  `tests/e2e/real/nilearn-visuals.spec.ts` → 1 passed (21.7s), quiet-check **PASS**, job
  `6d4c9fba24a84b08` succeeded with 4 artifacts. This affects every future Level B invocation
  in the program's own docs (§7's CR row) and should be corrected there too — flagged below.
- **`npm run dev:web` / `npm run dev:down` re-verified fresh**, on a throwaway scratch project
  (`TIT_DEV_PROJECT_DIR=<scratchpad>/hx-devproj TIT_DEV_PORT=8792`, never the shared project):
  Vite auto-walked past `5173`/`5174` (the maintainer's own session) to `5175`;
  `curl http://127.0.0.1:5175/api/version` → 200, empty cookie jar; `npm run dev:down` (same
  env) stopped and removed only the scratch container, leaving the shared one untouched
  (checked with `docker ps -a` before/after). Scratch project and its container fully removed
  afterward.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest -q` (before this lane's changes, freshly re-run) | 3258 passed, 18 skipped, 21 deselected, 34.72s |
| `python3 -m pytest tests/smoke/test_harness_selftest.py -q` (after) | **68 passed** (28 test functions, 2 parametrized over 21 rows; 7 of the 28 are the new payload-rename tests) |
| `python3 -m pytest -q` (final, after every other lane's concurrent additions too) | **3339 passed, 18 skipped, 21 deselected, 37.70s** — green |

Desktop gates not re-run: no file under `desktop/` was changed by this lane (the one real
Playwright spec run used the existing build from another lane, unmodified).

## Container restarts

**0.** Every file this lane touched is under `tests/smoke/**`/`dev/smoke.sh` (host-side,
pytest/bash only) or `dev/notes/**`; nothing under `tit/server/**`, `tit/jobs/**` or
`tit/catalog.py` was changed.

## Real runs (job-level, this lane's own submissions)

| # | Command | Result | Job id(s) |
|---|---|---|---|
| 1 | `dev/smoke.sh --list` (1 container) | printed, exit 0 | — |
| 2 | `dev/smoke.sh --list` (2 containers, fixture) | printed both, exit 0 | — |
| 3 | `dev/smoke.sh --smoke-kinds project_init` (2 containers, no selector) | ambiguous, exit 2 | — |
| 4 | `TIT_SMOKE_PROJECT_HOST=... dev/smoke.sh project_init` | 1 passed, 1.09s | `092bd589268e4645` |
| 5 | pass 1: `dev/smoke.sh analyzer_mesh analyzer_voxel stats_group nifti_average nilearn sim` | **7 passed**, 51.7s | see `results-20260904T010508Z-200417.md` |
| 6 | pass 2 (immediately after): same command | **7 passed**, 51.6s | see `results-20260904T010609Z-200517.md` |
| 7 | `desktop`: real `nilearn-visuals.spec.ts` via `--project=real`, offscreen | 1 passed, 21.7s, quiet-check PASS | `6d4c9fba24a84b08` |
| 8 | `dev/smoke.sh nilearn` (re-replay of the freshly-recorded real payload from #7) | 1 passed, 16.2s | `99fe6b776c3441d0` |
| 9 | `dev/smoke.sh --keep pre_qsiprep` (non-heavy; ran while another lane's `source` job was active) | 1 passed, 6.1s; manifest `keep: true`, `removed: false` | `471007265ae04b4e` |
| 10 | `npm run dev:web` / `npm run dev:down` on a scratch project, port 8792→Vite 5175 | proxy verified 200/empty-cookie; scratch container removed cleanly | — |

Every smoke- and scratch-tagged path created by these runs was removed by the harness itself or
by hand (the throwaway container, the scratch project directory) — verified with `find
/Users/idohaber/datasets/000 -iname "*smoke-*"` (outside `code/ti-toolbox/jobs/`) returning
nothing after run #9, and `docker ps -a --filter label=tit.stack=ti-toolbox-v3` showing only the
one shared container throughout.

## Open issues / requests to other lanes

1. **[docs, minor] `dev/notes/v3-pipelines-program.md` §7's own CR row says
   `npx playwright test --project real` — this form fails outright on the Playwright version in
   this worktree** (see §3 above for the exact error and fix). Suggested owner: whoever edits
   that program doc next, or the CR critic lane directly (it would otherwise hit this on its
   first Level B command).
2. **[not this lane's file] `desktop/tests/e2e/real/preprocess.spec.ts:93`** — D0's own
   `npm run typecheck` finding (`d0-notes.md` §7, a likely missing `await` before an `as` cast)
   was still present as of this session; not re-verified here since it is outside
   `tests/smoke/**`/`dev/smoke.sh` ownership.
3. **[informational, not this lane's]** the final on-disk sweep (`find
   /Users/idohaber/datasets/000 -iname "*smoke-*"`, run after every command in §3 above) found
   one path this lane did not create and did not touch:
   `derivatives/SimNIBS/sub-ernie/ex-search/smoke-ui-95104-ex` (mtime 20:17, `final_output.csv`
   + a plot + `run_config.json` — a real, apparently-succeeded run). Not this lane's row (`ex`
   is not among the rows this lane replayed) and not this lane's file ownership
   (`desktop/src/renderer/pages/optimizer/**`) — almost certainly lane FX1's own real proof of
   its ex/mEx fix, most likely still mid-session at the time of this check. Noted, not deleted.

## Files changed

- `tests/smoke/matrix.py` — `Row.payload_rename` field; five per-kind rename functions,
  documented next to the rows they apply to; wired onto `sim_ti`, `sim_mti`, `analyzer_mesh`,
  `analyzer_voxel`, `nifti_average`, `stats_group`, `nilearn`.
- `tests/smoke/test_kinds.py` — `load_submission` applies `row.payload_rename` to a loaded
  payload's config before building the `Submission`.
- `tests/smoke/test_harness_selftest.py` — 8 new tests for the rename mechanism; 2 pre-existing
  tests updated for the new behaviour on `sim_ti`/`nilearn`.
- `dev/smoke.sh` — `--list`; `describe_container` helper (shared by `--list` and the
  ambiguous-container die path); the `pipefail`/`grep` fix inside it.
- `dev/notes/v3-pipelines/RUNBOOK.md` — new, one page.
- `dev/notes/v3-pipelines/hx-notes.md` — this file.

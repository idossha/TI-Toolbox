# Lane D0 — dev mode (`npm run dev` is the whole system)

Contract: `dev/notes/v3-pipelines-program.md` §2 (decisions P1–P3), lane row D0 in §4.
Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed.
Date of every measurement below: **2026-09-03**, macOS 24.6.0 arm64, Docker Desktop, emulated amd64
image `idossha/ti-toolbox:dev`.

## 1. What now exists

```
npm run dev        .env.dev → attach/recreate/start the container → Vite → Electron, connected
npm run dev:web    the same without Electron → http://127.0.0.1:5173/
npm run dev:down   stop and remove this project's container
npm run dev -- --force   recreate a mismatched container even with jobs in flight
```

| Piece | File | What it does |
|---|---|---|
| Config | `desktop/.env.dev` (git-ignored) + `.env.dev.example` | `TIT_DEV_PROJECT_DIR` (required), `TIT_DEV_IMAGE_TAG` (`dev`), `TIT_DEV_PORT` (`8765`), `TIT_DEV_MOUNT_REPO` (`1`). Shell overrides the file. |
| Entry | `desktop/scripts/dev.ts` (tsx 4.23.13, new devDependency) | flags, config, one `ensureDevStack`, then Vite/Electron with the credentials in the child env |
| Env parsing | `desktop/scripts/devEnv.ts` | dotenv subset + validation; `DevConfigError` names the fix |
| Attach-or-start | `desktop/scripts/devStack.ts` | the Node `StackHost` + `ensureDevStack` / `stopDevStack` |
| Proxy | `desktop/scripts/devProxy.ts` | `createDevProxy` / `attachDevAuth`: bearer + Origin on `proxyReq` **and** `proxyReqWs` |
| Renderer-only | `desktop/scripts/devWeb.ts` | electron-vite's own `resolveConfig` + Vite's `createServer`, no Electron |
| One stack impl | `desktop/src/main/stack.ts` + new `stackHost.ts` | `StackHost` injection removed every `electron` import from the stack path |
| Container | `desktop/docker/docker-compose.v3.yml`, `container/blueprint/entrypoint.ti-toolbox.sh` | records `TIT_REPO_DIR`/`TIT_SERVER_RELOAD` on the container; `TIT_SERVER_RELOAD=1` → `--reload --reload-dir /ti-toolbox/tit` |
| Server | `tit/server/__main__.py` | new `--reload-dir` (repeatable), missing dirs warned and dropped |

### The refactor (P1's "no duplicate")

`stack.ts` used to import `electron`'s `app`, `./log` (imports `app`) and `./health` (imports `net`),
so attach-or-start could only run inside Electron main. A `docker run` in a shell script would have
drifted from the app's own container on the first change to labels, mounts or the health wait. The
four host-shaped needs now come through `StackHost` (`isPackaged`, `appPath`, `resourcesPath`,
`log`, `waitForHealth`, `fetchJson`); `src/main/stackHost.ts` binds the Electron half and exports the
one `stack` instance `index.ts` uses, `scripts/devStack.ts` binds the Node half. `grep -c electron
src/main/stack.ts` → 0 imports.

`start()` grew `StackStartOptions` — `preferredPort`, `imageTag`, `repoDir`, `serverReload`,
`requireMatch`, `forceRecreate` — all optional and all absent from the packaged app's own call, so
the launcher path is byte-for-byte the behaviour it had (proved by `launcher.spec.ts`, 11 tests).

### Two design points that were decided by measurement, not by taste

1. **`dev:web` does not use `electron-vite dev --rendererOnly`.** Measured on electron-vite 5.0.0:
   the flag only skips *rebuilding* main and preload; `createServer()` then calls
   `startElectron(inlineConfig.root)` unconditionally
   (`node_modules/electron-vite/dist/chunks/lib-7y7CgM8M.js`, the line right after
   `if (options.rendererOnly)`). My first `npm run dev:web` therefore launched Electron — the one
   thing a browser-only loop must not do, and under an agent also a monitor hijack. `devWeb.ts`
   resolves the same `electron.vite.config.ts` through electron-vite's exported `resolveConfig` and
   serves only `config.renderer` with Vite: no second copy of the renderer config, no Electron
   (verified: 0 Electron processes while `dev:web` runs).
2. **The published port is not part of the attach/recreate comparison.** First live start asked for
   `TIT_DEV_PORT=8766` and landed on **8781** — ports 8766–8780 were held by another agent's mock
   servers, and `findFreePort` walked past them, correctly. Had `describeMismatch` compared ports,
   every later `npm run dev` would have recreated that container to move a number nothing depends
   on. `TIT_DEV_PORT` is where the search starts; the dev script prints when the container ended up
   elsewhere and hands Vite/Electron the origin it actually has.

### The guard added after finding the sharp edge

A recreate stops the container **and mints a new bearer token**. During this workflow every other
lane talks to `http://127.0.0.1:8765` with the hard-coded token `devtoken`, and one lane had a `pre`
job running. So `npm run dev` now asks `GET /api/jobs` (with the token it recovered from the
container) before recreating and refuses when anything is `running`/`queued`/`pending`/`starting`,
naming the jobs and offering `dev:down` or `--force`. A server that cannot be asked reports no jobs
and the recreate proceeds — refusing there would make an unhealthy container impossible to replace.
Pure half unit-tested (`runningJobLabels`), plumbing verified live (72 jobs read through
`nodeStackHost.fetchJson`; a wrong token raises `HTTP 401`, which the guard catches).

## 2. Acceptance numbers (§2 of the plan)

| Acceptance item | Result |
|---|---|
| `GET http://127.0.0.1:5173/api/version` with **no cookie, no header** | **200**; same request straight to the container **401**; cookie jar after the request: **0 cookies** |
| `WS /ws/system` from a plain client (Origin `http://127.0.0.1:5173`) | through the proxy **OPEN + a snapshot frame** (`cpu_count,cpu_percent,disk,mem,processes,ts`); straight to the container **403** |
| the tab keeps working after the session store is cleared | `POST /auth/logout` through the proxy → **204**, then `GET /api/version` → **200** |
| after `docker restart` of the container the same tab keeps working, no reload | scratch container restarted (0.77 s), health back in **2 s**, then through the *same* running Vite: `/api/version` **200**, WS **OPEN + frame** |
| `npm run dev` under `TIT_E2E_OFFSCREEN=1` reaches `data-page="subjects"` with real subjects and no launcher | `DATA-PAGE subjects`; `SUBJECT-ROWS 4: 101 \| 102 \| ernie \| MNI152`; status bar `4 subjects · 3 m2m · 2 leadfields`; `LAUNCHER-SHOWN false`; CDP up **1 518 ms**, total **2 219 ms** |
| quiet check | **PASS** on both runs — 7 samples (dev probe) and 44 samples (specs); `no Electron/Chromium window reached the screen`, frontmost `Safari` → `Safari` |

The strict Origin proof was taken against the **scratch** container, which has no `TIT_DEV_ORIGINS`.
The shared container on 8765 still carries `TIT_DEV_ORIGINS=http://127.0.0.1:5173` from the old
manual flow, so a proxy that failed to rewrite `Origin` would still have been let through there —
the 403-vs-OPEN pair above is the honest measurement, and it does not depend on that variable.

## 3. Real runs

| # | What | Command | Wall time | Outcome |
|---|---|---|---|---|
| b1 | scratch start | `TIT_DEV_PROJECT_DIR=<scratchpad>/devproj TIT_DEV_PORT=8766 tsx ensure-scratch.ts` | **1 343 ms** | created `ti-toolbox-1fbdd9a3-tit-1`, published 8781, token 43 chars |
| b2 | scratch attach (2nd run) | same | **68 ms** | `attached=true`, same origin/token |
| b3 | scratch recreate (`TIT_DEV_MOUNT_REPO=0`) | same + `TIT_DEV_MOUNT_REPO=0` | **1 546 ms** | `Recreating the container — it mounts <worktree> at /ti-toolbox, this run wants (none)` |
| b4 | scratch recreate back (`=1`) | same | **1 515 ms** | `Recreating the container — it mounts (none) at /ti-toolbox, this run wants <worktree>` |
| b5 | entrypoint argv, reload off | `docker exec -e TIT_SERVER_RELOAD= … entrypoint.ti-toolbox.sh` (fake `simnibs_python`) | <1 s | `-m tit.server --project /mnt/devproj --host 0.0.0.0 --port 8781 --static-dir /opt/ti-toolbox/ui` |
| b6 | entrypoint argv, reload on | same with `TIT_SERVER_RELOAD=1` | <1 s | same **+ `--reload --reload-dir /ti-toolbox/tit`** |
| b7 | server under `--reload --reload-dir` in the container | `simnibs_python -m tit.server … --reload --reload-dir /ti-toolbox/tit` | 25 s (timeout) | `Will watch for changes in these directories: ['/ti-toolbox/tit']`, `Started reloader process using WatchFiles` |
| b8 | the same without `--reload-dir` (the failure it prevents) | `… --reload` | 12 s (timeout) | `Will watch for changes in these directories: ['/ti-toolbox']` — **5 834** dirs, of which **2 815** are `desktop/node_modules`, vs **54** under `tit/` |
| b9 | scratch container restart | `docker restart ti-toolbox-1fbdd9a3-tit-1` | 0.77 s + 2 s to healthy | tab-equivalent kept working (see §2) |
| b10 | scratch teardown | `TIT_DEV_PROJECT_DIR=… npm run dev:down` | <1 s | `stopped and removed ti-toolbox-1fbdd9a3-tit-1`; only `ti-toolbox-fad740e5-tit-1` left |
| c1 | `dev:web` vs scratch (strict, no `TIT_DEV_ORIGINS`) | `TIT_DEV_PROJECT_DIR=… nohup npm run dev:web` | attach 68 ms, Vite ~10 s (dep re-optimise) | 200 / 403-vs-OPEN / 204-then-200; **0 Electron processes** |
| c2 | `dev:web` vs the maintainer's container | `TIT_DEV_MOUNT_REPO=0 nohup npm run dev:web` → `/tmp/tit-dev.log` | attach <1 s | attached to `http://127.0.0.1:8765`; `/api/version` 200, WS OPEN, logout 204 then 200; **left running** at `http://127.0.0.1:5173/` |
| d1 | `npm run dev` (full, Electron) offscreen, CDP-driven | `bash scripts/e2e-quiet-check.sh node probe-dev-electron.mjs` | 2 219 ms to a rendered subjects page | quiet-check **PASS**, no launcher, 4 real subjects |
| e1 | the existing specs | `bash scripts/e2e-quiet-check.sh npx playwright test tests/e2e/launcher.spec.ts tests/e2e/native-launch.spec.ts` | **37.4 s** | **12 passed**, quiet-check **PASS** (44 samples) |

Scratch project: `<scratchpad>/devproj` (`dataset_description.json` + empty `sub-x/anat`), removed
from Docker at the end (b10); the directory itself is in the session scratchpad, not the repo.

## 4. Gates

| Gate | Result |
|---|---|
| `npm run typecheck` | **0 errors in D0's files.** The command as a whole fails on `tests/e2e/real/preprocess.spec.ts` (lane S2) — see open issues. |
| `npm run lint` | 0 errors, 3 pre-existing warnings (`react-hooks/incompatible-library` in `DataTable.tsx`/`VirtualList.tsx`) |
| `npx vitest run` | **57 files, 649 tests passed** (32 of them new: `tests/unit/dev-{proxy,env,stack}.test.ts`) |
| `npm run build` | ✓ built in 1.9–2.1 s |
| `python3 -m pytest -q` | **3 241 passed, 18 skipped, 21 deselected, 46.08 s**. Excluding lane S1's new `tests/smoke/`: 3 169 passed, **34.34 s** — the ~35 s budget is D0-clean; the growth past it is S1's new suite (plus a `pre` job running in the container at the time). |

New Python test: `tests/test_server_skeleton.py::test_reload_dir_scopes_the_watcher` — `--reload-dir`
reaches uvicorn as `reload_dirs`, a missing directory is warned about and dropped, and *no*
`--reload-dir` stays `None` (an empty list would be read as "watch nothing").

## 5. Container restarts

**0 restarts of the shared container `ti-toolbox-fad740e5-tit-1`.** One restart of the throwaway
scratch container `ti-toolbox-1fbdd9a3-tit-1` (b9), which was created and removed by this lane.
`GET /api/jobs` was checked before every risky step. (The shared container was restarted by another
lane at ~18:13 — not by D0.)

## 6. Known gaps, and what the orchestrator has to do after the workflow

1. **The image still has the old entrypoint.** `entrypoint.ti-toolbox.sh` lives *inside*
   `idossha/ti-toolbox:dev`, not on the bind mount, so `TIT_SERVER_RELOAD=1` is recorded on a
   container but ignored until the image is rebuilt. I did not rebuild: the tag is shared with every
   other lane. The change is proved by running the new script *from the mounted worktree* inside the
   container (b5/b6) and by running the resulting command line for real (b7). **After the workflow:
   rebuild `idossha/ti-toolbox:dev` (`container/blueprint/Dockerfile.ti-toolbox`, which already
   `COPY`s the entrypoint and installs `uvicorn[standard]`, i.e. watchfiles).**
2. **The shared container predates the compose change.** `ti-toolbox-fad740e5-tit-1` was created by
   hand: it *has* the worktree at `/ti-toolbox` and `PYTHONPATH=/ti-toolbox`, but its environment
   carries neither `TIT_REPO_DIR` nor `TIT_SERVER_RELOAD`, so `describeMismatch` reports "no repo
   mounted" and `npm run dev` with the intended `TIT_DEV_MOUNT_REPO=1` would recreate it — killing
   the other lanes' jobs and replacing `devtoken` with a fresh random token. **`desktop/.env.dev`
   therefore ships `TIT_DEV_MOUNT_REPO=0` today, with the reason written in the file. After the
   workflow: flip it to 1, then `npm run dev` (it will recreate the container, with the reload
   entrypoint, once the image is rebuilt).** The new jobs guard makes an accidental recreate a
   readable refusal rather than a silent kill.
3. **`npm run dev` leaves nothing behind on Ctrl-C in a terminal** (the signal reaches the process
   group), but a bare `SIGTERM` to the `npm` process alone does not reach Electron — measured: a
   first probe run left an orphan Electron holding the CDP port. Anything scripting `npm run dev`
   should spawn it `detached: true` and kill the group, as the D0 probe now does.

## 7. Requests to other lanes

- **S2** — `desktop/tests/e2e/real/preprocess.spec.ts:93` fails `npm run typecheck`
  (`error TS2352: Conversion of type 'Promise<any>' to type '{ group_id: string; jobs: JobStatusLite[] }'`,
  plus several `Property 'id' is missing in type 'Promise<any>'`). It looks like a missing `await`
  before a `as` cast. The desktop typecheck gate is red for every lane until it is fixed; D0's own
  files are clean.
- **S1** — the host `pytest -q` wall time went 34.34 s → 46.08 s when `tests/smoke/` landed; §4 of
  the program budgets ~30–35 s. Worth checking whether the smoke selftests can be trimmed or gated.
- **Nobody, informational** — `desktop/docker/docker-compose.v3.yml`, `desktop/tsconfig.node.json`
  and `desktop/tsconfig.web.json` are not named in any lane's ownership row; D0 edited all three
  (two compose `environment:` entries, and a `scripts/**/*.ts` include so the new files typecheck).
  No other lane touches them.

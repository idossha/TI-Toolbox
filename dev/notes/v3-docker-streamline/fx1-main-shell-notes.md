# FX1 — desktop main + shell (fix lane, 2026-09-03)

Closes QA engineer findings 1 (BLOCKER), 5 and 6, plus the shell half of QA designer finding 4.
Findings 4 (HEAD parity) and 7 (stale `docker_engine.py` docstring) belong to FX3 and were not
touched.

Everything below was measured, not read: unit tests against the real modules, the three owned e2e
specs against the fake Engine API, and two offscreen runs against **real Docker and the real
`idossha/ti-toolbox:dev` image** with my own container on my own temp project directory. The
maintainer's container `ti-toolbox-fad740e5-tit-1` was inspected read-only and never stopped,
restarted or given work; my own container was removed at the end (`docker ps -a --filter
label=tit.stack=ti-toolbox-v3` shows only the maintainer's).

---

## 1. BLOCKER — every stack start bind-mounted a host directory over `/ti-toolbox`

**Confirmed live before the fix**, on the maintainer's own running container:

```
$ docker inspect ti-toolbox-fad740e5-tit-1 --format '{{json .HostConfig.Binds}}'
[..., "/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui:/ti-toolbox"]
```

`/ti-toolbox` is not spare space in the image: `container/blueprint/Dockerfile.ti-toolbox:214`
checks the repo out there and line 227 pip-installs `tit` from it. The mount replaces the image's
own toolbox for the container's lifetime — silently in dev, fatally once packaged
(`app.getAppPath()/..` is `TI-Toolbox.app/Contents/Resources`, which has no `tit` in it).

Three changes, each of which independently would have been enough, together making the property
hold end to end:

1. `src/main/stack.ts#resolveRepoDir(env, isPackaged)` — now exported and pure. Returns `undefined`
   unless `TIT_DEV_REPO_DIR` (or `TIT_REPO_DIR`, accepted as the same request) is set **and**
   `app.isPackaged` is false. No implicit fallback of any kind.
2. `src/shared/compose.ts#buildStackEnv` — always sets `TIT_REPO_DIR`, to `""` when there is no
   request. This is load-bearing rather than cosmetic: `stack.ts` interpolates the compose file
   from `{...process.env, ...buildStackEnv(...)}`, so simply *omitting* the key would let a stray
   host `TIT_REPO_DIR` re-enable the mount, including in a packaged app.
3. `src/shared/composeFile.ts#parseService` — a volume entry whose source interpolated to empty is
   dropped whole (`":/ti-toolbox"` → no bind), instead of `parseBind` throwing "empty source". An
   empty *target* is still an error: an optional mount is an empty source, not a broken line.
   `docker/docker-compose.v3.yml` and `tests/e2e/fixtures/compose-v3.fixture.yml` now both spell it
   `${TIT_REPO_DIR:-}:/ti-toolbox`.

**Live proof, real engine + real image, offscreen** (`scratchpad/fx1-verify.cjs`, temp project dir
with a copied `dataset_description.json`, never `~/datasets/000`):

```
stack.start → {"ok":true,"attached":false}
HostConfig.Binds: ["<temp project>:/mnt/fx1proj",
                   "/Users/idohaber/.config/ti-toolbox:/root/.config/ti-toolbox",
                   "/var/run/docker.sock:/var/run/docker.sock"]
PASS: no /ti-toolbox bind
container tit: /ti-toolbox/tit/__init__.py     <- the image's own, intact and importable
```

**And the opt-in still works** (`scratchpad/fx1-verify-dev.cjs`, same real engine, with
`TIT_DEV_REPO_DIR=<worktree>`): the bind reappears —
`[..., "/Users/idohaber/.../v3-electron-gui:/ti-toolbox"]`.

Tests: `tests/unit/docker-stack.test.ts` (5 cases on `resolveRepoDir`, including the packaged case
with the env var set), `tests/unit/composeFile.test.ts` (4 fixture cases + one asserting it
directly against the *shipped* file's `HostConfig.Binds`), `tests/unit/compose.test.ts` (the key is
present and empty, not absent), `tests/e2e/launcher.spec.ts` (no `:/ti-toolbox` bind by default; a
dedicated test with `TIT_DEV_REPO_DIR` set that asserts the bind is there).

## 2. MEDIUM — attach trusted the 32-bit project hash alone

`tryAttach`'s decision is now a pure exported function, `decideAttach(existing, hostProjectDir)`,
so the case that matters — a hash collision — is testable without staging one:

- `attach` only when the container's `tit.host_project_dir` label resolves (through `realpath`, so
  symlinked paths match) to the requested directory.
- `refuse` — a `StackStartError` naming the container and the other directory — when a **running**
  container carries this project's name but a different (or absent) host-dir label. Removing it was
  not an option: another project may be actively using it, and the user can see both.
- `recreate` when the only collisions are stopped containers (they hold the name; removing one
  destroys nothing, named volumes are kept).

A missing label is treated as a mismatch, deliberately: there is nothing to compare against.
Checked against the live container first — it does carry `tit.host_project_dir`, so no existing
stack is orphaned by this.

Tests: 7 cases in `tests/unit/docker-stack.test.ts`, including a real symlink (`/tmp` vs
`/private/tmp` on macOS is exactly this class of false negative).

## 3. MEDIUM — no in-app stop, and a silent leftover container on quit

**In-app stop.** New Docker card in `pages/settings` showing the container name, the image tag, the
Docker healthcheck verdict, and a `Stop Docker stack` button. It renders only when this app owns a
running stack, so browser mode and manual-connect sessions are unaffected.

**No preload growth.** ADR row 14 budgets 12 top-level bridge entries and it is still exactly 12 —
`src/preload/index.ts` is untouched. `stack.stop()` and `stack.status()` already existed; what
changed is in main: `tit:stack:stop` widened from `fromLauncherWindow` to `fromMainWindow`, and
`tit:stack:status` grew `containerName`/`image`/`health`. The widening is safe by construction: the
page that can call it is served *by the container it stops*, so it can only end its own session —
no other project, no host path, no new mount. A stop from a server-served page returns the window
to the launcher (otherwise it would sit on a UI whose backend just died).

**Quit notice.** `handleQuitRequest` now calls `noteStackLeftRunning(containerName)` when a stack is
up and no jobs are running: always a log line, plus a native notification where system UI is
allowed. Non-blocking, and the running-jobs dialog is untouched, as briefed.

**Live proof, real engine + real image, offscreen** (same run as §1, fresh renderer served to the
container via the project mount so the UI under test is the one just built):

```
stack.status → {"running":true, ..., "containerName":"ti-toolbox-280701e7-tit-1",
                "image":"idossha/ti-toolbox:dev","health":"starting"}
Docker card: Docker | Container | ti-toolbox-280701e7-tit-1 | Image | idossha/ti-toolbox:dev |
             Health | starting | Quitting leaves this container running ... | Stop Docker stack
back on launcher after Stop in 3.0 s
PASS: container removed by Stop
```

Tests: `tests/e2e/launcher.spec.ts` — the launcher-only refusal test no longer lists `stack.stop`,
and a new test asserts the connected app can stop its own stack, that `status` carries the three
new fields, that the container is gone, and that the window lands back on the launcher.

## 4. Designer finding 4, shell half — the rail keeps 216px at the design's own floor

`src/renderer/app/shell.css` collapses to the 56px icon rail at `max-width: 1280px` (inclusive; it
was `1279px`, chosen so the full rail would survive the screenshot width). `NavRail.tsx`'s
`ICON_RAIL_QUERY` matches the same literal, and `cssRules.test.ts` now asserts both, plus that no
`max-width: 1279px` / `1199px` rule remains. The stylesheet carries the reasoning: 1280 is the
*floor* of the sizes this app is designed for, not a size with room to spare.

Measured effect, from `preprocess.spec.ts`'s own console line at 1280×800:
`.shell-content` x = 56 (was 216+ nav), `.page-layout-main` width = **860 px, up from the 700 px QA
measured**. Nav accessibility is unaffected — every `NavLink` already carries `aria-label`, so
`getByRole("link", {name})` still resolves in the collapsed state (19/19 owned e2e green, and
gallery/panels/results/jobs/help/quick-notes/analyzer all still pass).

860 is still 20 px short of DESIGN.md §8's ≥880 floor; the rest is the inspector/header half of the
same finding, which is FX2's.

---

## Gate

| Gate | Result |
|---|---|
| `npm run typecheck` | pass |
| `npm run lint` | pass (0 errors, 3 pre-existing `react-hooks/incompatible-library` warnings) |
| `npx vitest run` | **496 passed / 46 files** (was 488/45) |
| `npm run build` | pass |
| `e2e-quiet-check npx playwright test launcher settings smoke` | **19 passed**, "no Electron/Chromium window reached the screen" |
| real-engine offscreen run (own container, temp project) | pass — see §1 and §3 |

Broader e2e sweep for the rail change (gallery, panels, results, jobs, help, quick-notes, analyzer,
preprocess): **19 passed, 1 failed**, and the failure is not mine —
`preprocess.spec.ts:147 "has no page header, and the work pane keeps the height that bought"`
expects `main.y - shell.y <= 4` and measures 24. That is a *vertical* assertion in a spec another
lane rewrote at 13:04 today (designer finding 7, the Preprocess page header); every change in this
lane is horizontal and nav-rail-scoped. Flagged, not touched.

## Files changed

- `desktop/src/main/stack.ts` — `resolveRepoDir` (exported, pure, opt-in), `sameHostDir`,
  `decideAttach`; `CurrentStack`/`StackStatusResult` carry container name, image and health.
- `desktop/src/main/index.ts` — `stack:stop` sender check widened + return-to-launcher;
  `stack:status` payload; `noteStackLeftRunning` on quit.
- `desktop/src/shared/compose.ts` — `buildStackEnv` always emits `TIT_REPO_DIR`.
- `desktop/src/shared/composeFile.ts` — drop a volume entry with an empty interpolated source.
- `desktop/src/shared/tit-bridge.d.ts` — status fields, `stop` doc, ADR row-14 note.
- `desktop/docker/docker-compose.v3.yml` — `${TIT_REPO_DIR:-}` + header rewrite.
- `desktop/src/renderer/pages/settings/index.tsx` — the Docker card.
- `desktop/src/renderer/app/shell.css`, `desktop/src/renderer/app/NavRail.tsx` — 1280 inclusive.
- `desktop/tsconfig.web.json` — include `src/main/{stack,hostInfo,userConfig}.ts` so the new pure
  functions can be unit-tested (same precedent the file already sets for `window.ts`,
  `nativeRuntime.ts` and `docker/**`).
- Tests: `tests/unit/{compose,composeFile,docker-stack,cssRules}.test.ts`,
  `tests/e2e/launcher.spec.ts`, `tests/e2e/fixtures/compose-v3.fixture.yml`.

## Follow-ups (not mine to fix)

1. `docker-compose.v3.yml` still sets `PYTHONPATH: /ti-toolbox` unconditionally. Harmless today
   (that is the image's own repo path, and `tit` is pip-installed anyway), but the final image
   stage sets no `PYTHONPATH` of its own, so if any baked tool ever needs one this line silently
   wins. W2/FX3 call.
2. `electron-builder.yml` still copies nothing to where `resolveComposeFile()`'s
   `process.resourcesPath` candidate looks (QA engineer finding 8) — finding 1's packaged path is
   fixed, but still unexercised because no packaged Docker-mode build exists yet.
3. The e2e suite remains uncovered by CI (QA engineer finding 2) — out of this lane's scope.

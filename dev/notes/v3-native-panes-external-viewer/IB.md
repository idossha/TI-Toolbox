# Lane IB — build the image from the local checkout, with a real embed

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-06 (night).
Follows **VE** (`VE.md` §4.2, §6.1–6.3): the image could not be built because the recipe
`git clone`d a ref that is not pushed, and no Tetravox release carries the embed. Both blockers
are removed in code. **The image itself is not built**: the host disk filled mid-build and
Docker Desktop went down. §4 says exactly where it stopped.

## 1. Build from the checkout, not from GitHub

`Dockerfile.ti-toolbox` now has two `source` variants selected by a global `ARG
TI_TOOLBOX_SOURCE` used in a `FROM`:

| `TI_TOOLBOX_SOURCE` | stage | context |
|---|---|---|
| `local` (default) | `source-local`: `COPY . /ti-toolbox` | the repository root, filtered by the new repo-root `.dockerignore` |
| `clone` | `source-clone`: `git clone --branch $TI_TOOLBOX_REF` | an empty staging dir |

Only the selected stage is built. `build.sh` maps `--ref <git-ref>` to `clone` (and keeps
`--ti-toolbox-ref` as the old name); no `--ref` means `local`. In clone mode it refuses a ref
`git ls-remote` cannot see, with the reason — the failure VE hit is now one sentence instead of
a `cache key … not found` from inside BuildKit. `git clone --branch` takes branches and tags, not
raw shas; the README says so.

The entrypoint is now `COPY --from=source`, so a `--ref` build runs the ref's entrypoint and a
local build the checkout's; the context no longer has to carry it. The `source` stages and the
UI's Node stage run on `$BUILDPLATFORM` (natively on this Mac); only the SimNIBS stage is
emulated.

**`.dockerignore` is an allow-list** (`*`, then `!tit !resources !contracts !container !desktop
!pyproject.toml !README.md !LICENSE`, then `desktop/{node_modules,out,release,dist,test-results,
tests,.*}` back out). Measured in the `source-local` stage:

| | |
|---|---|
| raw tree | ~2 GB (`desktop/node_modules` 1.3 GB, `desktop/.runtime-staging` 166 MB, `desktop/tests/e2e/artifacts` 144 MB, `docs` 250 MB) |
| first cut (`desktop/.*` not excluded) | 262.8 MB transferred — `.runtime-staging` was inside |
| final | **137.5 MB** (`resources` 108 MB, `tit` 23 MB, `desktop` ~5 MB, `contracts` 1 MB) |

The v2 recipes use `container/blueprint` itself as context and are untouched by the file.

**Build record.** The final stage writes `/etc/ti-toolbox-build.json` —
`{version, sha, short, dirty, source, ref, date}` — from `--build-arg`s `build.sh` computes:
`git rev-parse HEAD`, `git status --porcelain --untracked-files=no` (tracked files only; an
untracked scratch file is not a different build), UTC date; a `--ref` build takes the sha from
`ls-remote` and is never dirty. `org.opencontainers.image.revision` now carries the full sha.
`/api/version` does **not** expose it: the route reports no build id today and its `Version`
model is in the frozen contract (`contracts/openapi.v1.yaml`), so adding a field is a contract
change for whoever owns that, not a side effect of this lane.

## 2. Embed source

Built from the Tetravox worktree `/Users/idohaber/00_development/tetravox-wt-embed-release`
(`feat/embed-release`, PR #35, HEAD `ebd814b`; nothing committed or pushed there — `git status`
clean after):

```
pnpm install --frozen-lockfile              (wasm pkg already present; `pnpm wasm` skipped)
pnpm --filter @tetravox/embed build
pnpm --filter @tetravox/embed pack:embed    -> packages/embed/dist-pkg/tetravox-embed-0.3.11.tgz  1.8 MB
sha256 977dc249e90ad8d56abf7d9f1629abdddf5a919f7d3d73a86a6c92d9838624a2
manifest {"name":"@tetravox/embed","version":"0.3.11","protocol":2,"sha":"ebd814b7…"}
```

Protocol 2 is inside `tit/tetravox/protocol.py`'s `[1, 2]`. Layout is release-shaped
(`<name>-<v>/{dist/, manifest.json, LICENSE, EMBED.md, *.schema.json}`), which is what the bake
stanza expects.

Served with `python3 -m http.server 8798 --bind 0.0.0.0` from `dist-pkg/` — **8799 was taken**
by a stale `http.server` (pid 63027) from an earlier session, serving an *empty* `dist-pkg` of
the other Tetravox worktree; left alone. `host.docker.internal:8798` resolved from an amd64
build-network container and the digest matched before the build was started.

`build.sh` gains `--tetravox-sha256 <hex>`, **required** with `--tetravox-tgz`: the resolver
reads a release's `.tgz.sha256` sidecar, but a hand-given URL has none, and the Dockerfile
(VE §2.3) will not unpack an unverified archive into a served directory. The old behaviour
was a `WARNING … not verified` on stderr and an unverified extract; that path is gone.

## 3. Two defects found before the SimNIBS stage

Both would have failed a `--ref` build too; neither is a recipe bug.

1. **`desktop/package-lock.json` was stale.** `npm ci` in the UI stage: "Missing:
   @xyflow/react@12.11.6 … zustand@4.5.7 from lock file" — the pipeline-canvas lane added
   `@xyflow/react` through pnpm (`pnpm-lock.yaml` has it, `package-lock.json` did not). CI's own
   `npm ci` job (`.circleci` L294) and `release-build.yml` use the npm lock, so CI was broken by
   the same drift. Regenerated with `npm install --package-lock-only --ignore-scripts` (+240
   lines, `node_modules` untouched). Two lockfiles in `desktop/` with two package managers is
   how this happens; one should go.
2. **The isolated `fastsurfer` stage could not download checkpoints.**
   `download_checkpoints.py` → `FastSurferCNN.utils.checkpoint` → `import torch` at module
   level; the stage installs only `requests`. The Dockerfile's own comment said this was
   "NOT verified" and "the first place to look". Moved the download to the final stage after
   `pip install -e $FASTSURFER_HOME` (where the layered recipe ran it and it was proven); the
   `fastsurfer` stage now only vendors the clone.

One non-defect: the second attempt failed on `Could not resolve "./notebooks.css"` — the
notebooks lane wrote that file 30 s after my context snapshot. A live worktree with three lanes
editing is a moving build input; `dirty:true` in the build record is the honest label for it.

## 4. Where the build stopped

Attempt 4 (`/tmp/image-build-embed.log`, started 01:12 UTC, sha `8a67eb76`, dirty):
`source-local`, `ui-builder` (`npm ci && npm run build` — passed, native arm64), `fastsurfer`
clone, apt layers and the Docker-CLI layer of the final stage all built. During the SimNIBS
installer step (`RUN wget … simnibs_installer_linux.tar.gz && … install -s`):

```
free: 11 GiB at start → 8.9 GiB (20:14) → 172 MiB (20:16)
#21 ERROR: error committing …: write /var/lib/docker/buildkit/containerd-overlayfs/metadata_v2.db: input/output error
```

then the Docker socket disappeared: Docker Desktop went down with the disk (`Docker.raw`
apparent 994 GB, **296 GB on disk**; `docker system df` before the build reported 47.5 GB of
reclaimable images, 40.7 GB of build cache, 26.8 GB of unused volumes). The 3 GiB floor from the
brief was crossed inside one two-minute poll, so the stop was after the fact. The maintainer's
dev container `ti-toolbox-fad740e5-tit-1` is down with the daemon; it was not recreated or
touched, and comes back with Docker. Nothing of the maintainer's was deleted to make room.

**Not done, in order, once there is disk** (the exact commands are in
`container/blueprint/README.md` → "Which Tetravox gets baked", and the verification script is
already written at `<scratchpad>/verify-image.sh` — recreate from §5 if the scratchpad is gone):

1. `docker system prune` / `docker builder prune` as the maintainer sees fit (≥ 100 GB is
   reclaimable inside `Docker.raw`); re-run `build.sh --tag idossha/ti-toolbox:dev
   --tetravox-tgz http://host.docker.internal:8798/tetravox-embed-0.3.11.tgz --tetravox-sha256
   977dc2…` with the http.server restarted (it was stopped at the end of this lane).
2. In the image: `/opt/tetravox/embed/manifest.json` (0.3.11 / protocol 2),
   `/etc/ti-toolbox-build.json`, `simnibs_python -c "import tit, simnibs, nbformat,
   jupyter_client"`, `/opt/fastsurfer/checkpoints` populated.
3. Throwaway container on 8766 (`-e TIT_SERVER_TOKEN=ib -e PROJECT_DIR_NAME=000 -v
   /Users/idohaber/datasets/000:/mnt/000`): `/api/health`, `/api/capabilities`
   (`tetravox_embed.available true, protocol 2, source baked`), `/tetravox/` 200 with the
   `wasm-unsafe-eval` CSP, `/tetravox/manifest.json`, `/tetravox/nope.js` 404.
4. `TIT_E2E_SERVER_URL=http://127.0.0.1:8766 TIT_E2E_TOKEN=ib npx playwright test --project
   real tests/e2e/real/tetravox.spec.ts tests/e2e/real/viewer-open.spec.ts` (offscreen by
   default on macOS via `_helpers.offscreenEnv`). **`/tmp/tit-e2e.lock` holds pid 50371, which
   is dead** — a stale lock; take it over rather than wait on it.

`tests/e2e/real/viewer-open.spec.ts` is new and type-checks: it asserts the served manifest is
not the placeholder and carries the CSP, then does Subject ernie → Viewer → Simulation /
Thalamus → Open → `viewer-sub-viewer` active → `tetravox-host[data-viewer-status=ready]` with a
60 s budget (a real bundle, not the mock's). Written, not yet run.

## 5. Verification script (as prepared)

```bash
IMG=idossha/ti-toolbox:dev
docker run --rm $IMG cat /opt/tetravox/embed/manifest.json /etc/ti-toolbox-build.json
docker run --rm $IMG simnibs_python -c "import tit, simnibs, nbformat, jupyter_client"
docker run -d --name tit-ib-smoke -p 127.0.0.1:8766:8765 -e PROJECT_DIR_NAME=000 \
  -e TIT_SERVER_TOKEN=ib -v /Users/idohaber/datasets/000:/mnt/000 $IMG
H="Authorization: Bearer ib"; B=http://127.0.0.1:8766
curl -s -H "$H" $B/api/health; curl -s -H "$H" $B/api/capabilities | python3 -m json.tool | grep -A12 tetravox_embed
curl -sD - -o /dev/null -H "$H" $B/tetravox/ | grep -i "HTTP\|content-security"
curl -s -H "$H" $B/tetravox/manifest.json; curl -s -o /dev/null -w '%{http_code}' -H "$H" $B/tetravox/nope.js
docker rm -f tit-ib-smoke
```

## 6. Other changes

- `.circleci/config.yml`: the image job passes `--ref "${CIRCLE_TAG:-$CIRCLE_BRANCH}"` (the ref
  is pushed by definition there) and the smoke step asserts `/etc/ti-toolbox-build.json` has a
  40-hex sha. **The job's time budget is unchanged and still the open question VE §5.4
  raised**: a from-scratch SimNIBS install against a 15 m `no_output_timeout` on a 2-vCPU
  executor. Dropping `--ref` there would build the exact commit from the checkout instead of
  the branch tip; both are documented in the job.
- `container/blueprint/README.md`: local-context build, `--ref`, the embed-source recipe,
  `--tetravox-sha256`, the build record, the "until 0.3.12 ships" note, the CI section.
- `docs/wiki/desktop-app.md` does not describe the build; unchanged.
- The watcher pattern `pgrep -f container/blueprint/build.sh` matches the watcher itself.
  Both of mine hung on it after the build died and had to be stopped by hand; match on
  `docker build` or a pidfile next time.

---

## Slimming the Dockerfile (2026-09-06, later)

395 lines -> 162. Maintainer: "the dockerfile.ti-toolbox looks way too long and complicated";
follow-up: "make sure we do not have gmsh or anything unnecessary installed in the container."

Rationale that is worth keeping lives in `container/blueprint/README.md` ("What the image
deliberately does not contain"), not in the Dockerfile. This file records only the measurements.

### Method

Every removal was justified by a grep over `tit/` (and, for gmsh, over the installed `simnibs`
package inside the image) and then proved by a full rebuild plus a live smoke test. Three builds:
one to prove the pip set resolves with no compilers, one to add the gmsh prune, one to restore
the five `libX*`/`libICE`/`libSM`/`libxkbcommon` packages that `bpy`'s `.so` links (dropping the
whole X11 set had broken `import bpy` — the only regression the pass produced, caught by the
import smoke).

### gmsh

- `simnibs_env/lib/libgmsh.so.4.14` = 92 MB. `grep -rl libgmsh` over the whole env matches only
  `gmsh.py`, its `.pyc`, the dist-info RECORD, a cmake target file and two doc CMakeLists — no
  `.so` and no binary under `simnibs/external/bin/linux` links it (`ldd` on each: clean).
- `grep -rn "^import gmsh"` over `simnibs/`: exactly one hit, `simnibs/cli/gmsh_cli.py` — the
  Gmsh GUI launcher `/api/viewers/gmsh` used to drive, removed by D3.
- `simnibs/mesh_tools/gmsh_view.py` is imported at module load by `sim_struct.py`,
  `tes_flex_optimization.py`, `tdcs_optimization.py` and `tms_coil.py`, so it stays — but it
  only writes `.opt` files and never imports the `gmsh` module. Proved after the prune:
  `import simnibs.mesh_tools.mesh_io, simnibs.simulation.sim_struct,
  simnibs.optimization.tes_flex_optimization.tes_flex_optimization` succeeds while
  `import gmsh` raises ModuleNotFoundError and `which gmsh` finds nothing.

### Size (docker images, before / after)

| | Disk usage | Content size |
|---|---|---|
| before | 19.5 GB | 5.88 GB |
| after | 9.27 GB | 2.41 GB |

Biggest remaining entries, all justified: `bpy` 821 MB (the `blender` job kind),
`torch` 697 MB + FastSurfer checkpoints 67 MB (`--seg_only`), `simnibs` 393 MB (221 MB of it
segmentation atlases charm needs), `SimpleITK` 265 MB, `PyQt5` 202 MB, `llvmlite` 162 MB — the
last three are SimNIBS's own vendored environment, not ours to prune from a pip line.

### Verified against `idossha/ti-toolbox:dev` (d981927f6cca)

- `import tit, simnibs, simnibs.segmentation, brainnet, torch, mne, h5io, nbformat,
  jupyter_client, ipykernel, bpy, nilearn, trimesh, meshio` — all OK (torch 2.7.1+cpu).
- `import tit.sim, tit.opt, tit.analyzer, tit.stats, tit.pre, tit.blender,
  tit.tools.nifti_to_mesh` — OK.
- `simnibs_python -m tit.server --help`, `dcm2niix -h`, `docker --version` — OK.
- `jupyter kernelspec list` shows `simnibs`; `POST /api/kernels` starts it and one
  `{"op":"execute"}` over `/ws/kernels/{id}` returns stdout + `execute_result` 42, then idle.
- Container healthy in ~20 s; `/api/health`, `/api/version`, `/api/capabilities`
  (`tetravox_embed`: baked, 0.3.11, protocol 2, compatible), `/tetravox/` 200 with its CSP,
  `/tetravox/nope.js` 404. Build record and OCI labels present.

### PyQt5 and TMS coil models (2026-09-06, maintainer's answer on the UNSURE list)

Removed in the same prune `RUN`. Proof, run inside the image before and after:

- `grep -rn PyQt5 site-packages/simnibs --include='*.py' | grep -v /GUI/` -> 4 hits, all in
  `cli/postinstall_simnibs.py` (install time). In `tit/`, every Qt import is under `tit.gui`
  (not shipped), plus `tit/project_init/first_time_user.py` — imported only from
  `tit/gui/main.py:624` — and one lazy in-function import in `tit/telemetry.py:652`.
- `grep -rln coil_models site-packages/simnibs` -> the TMS example, `tms_flex_optimization.py`,
  `cli/download_coils.py`, `sim_struct.py`'s TMS classes and `utils/file_finder.py:63`, which is
  an `os.path.join` with no existence check. After removal, `from simnibs import sim_struct` and
  a `SESSION` + `TDCSLIST` with two 50x50 rect electrodes construct fine
  (`TDCSLIST 2 [0.001, -0.001]`).
- `import PyQt5` and `import simnibs.GUI` now both raise ModuleNotFoundError while every
  runtime import listed above still succeeds, the kernel still starts and executes, and
  `verify-image.sh` is unchanged (healthy, embed 0.3.11 protocol 2 baked, `/tetravox/` 200).

8.93 GB disk / 2.32 GB content (from 9.27 / 2.41).

# v3 Docker-centric streamlining — plan of record (2026-09-03)

Supersedes the *deployment* parts of `dev/notes/v3-native-desktop-plan.md` (whose spikes and research
remain the evidence base; the native runtime is parked, not deleted). Maintainer's direction, verbatim:
*"keep docker but streamline everything else. meaning still have the centralized docker images with
fastsurfer in it including the tetravox installation … the installation should be shipped within the
docker. ti-toolbox just calls it and interfaces with its API to automate loading of data … keep compose,
drive it via Engine API … [native mode] decide later."*

## 0. Decisions (ADR rows 22–26)

| # | Decision |
|---|---|
| D1 | **One image, `idossha/ti-toolbox:<ver>`** (amd64): SimNIBS 4.6 + `tit` + `tit.server` baked in (no pip install at start) + the built desktop UI at `/opt/ti-toolbox/ui` + **Tetravox Embed** at `/opt/tetravox/embed` + **FastSurfer `--seg_only`** at `/opt/fastsurfer` with checkpoints pre-downloaded. QSIPrep/QSIRecon stay separate images pulled on demand for DWI. |
| D2 | **FreeSurfer image dropped.** `recon-all`, thalamic-nuclei and hippocampal-subfield stages, the `freesurfer` compose service, the `freesurfer_data` volume and the FS license plumbing for the core are removed. Existing recon-all derivatives on disk keep working (readers accept both). QSIPrep's own FreeSurfer use for ACT stays QSIPrep's business (license passed only when DWI runs with that option). |
| D3 | **X11 removed** everywhere: no `/tmp/.X11-unix` or `.Xauthority` mounts, no `DISPLAY`, no `xhost`, no `x11.ts`; Freeview and Gmsh launchers deleted. Viewing = Tetravox Embed rendered in the Electron window (host GPU) from the container-served bundle; TI-Toolbox drives it over the postMessage protocol. |
| D4 | **Compose stays the stack definition, the Engine API drives it.** `desktop/docker/docker-compose.v3.yml` (one `tit` service) is read by the app and realised through the dependency-free Engine API client (`desktop/src/main/docker/`): pull with progress, create/start, logs/events, stop. The docker CLI is used only for `docker context inspect`. Supported engines: Docker Desktop, Docker Engine; Colima/OrbStack best-effort; Podman unsupported until spiked. |
| D5 | **Native (no-Docker) mode parked**: `nativeRuntime.ts`, `electron-builder.yml`, the runtime build scripts and `dev/spikes/native/` stay in the tree, off by default, untouched by this program. |
| D6 | **Cross-platform fixes from Stage N0 are kept**: Windows-safe job control, FreeSurfer-binary removal (`segstats.py`, nibabel reslice, vendored fsaverage), `tit.job_id` labels, resource-path resolver, Engine API clients. |

## 1. Architecture

```
Host                                                          idossha/ti-toolbox:<ver> (amd64)
┌─ Electron shell ───────────────────────────────┐            ┌────────────────────────────────────────────┐
│ main: Engine-API client ─ compose.v3.yml ──────┼─ socket ──▶│ entrypoint → simnibs_python -m tit.server   │
│ renderer (served by the container, :port) ─────┼─ http ────▶│   /            → /opt/ti-toolbox/ui         │
│   └─ <iframe src=/tetravox/index.html?embed=1> │            │   /tetravox/   → /opt/tetravox/embed (CSP)  │
│        WebGL2+WASM on the host GPU  ◀─ files ──┼───────────▶│   /api/files/raw/{path}  (jailed stream)    │
│        postMessage: load/setCursor/screenshot… │            │   /api/view/{kind} → Tetravox ViewSpec v2   │
└────────────────────────────────────────────────┘            │ jobs: charm · subject_atlas · FastSurfer    │
      docker.sock mounted for DWI (QSIPrep/QSIRecon)          │       seg_only · tit.sim/opt/analyzer/stats │
                                                              └────────────────────────────────────────────┘
```

Contracts:
- **Embed protocol v1** — owned by tetravox `docs/EMBED.md` (branch `feat/embed`); summary in `dev/notes/v3-ux-redesign-plan.md` §4.5. Embed URL `/tetravox/index.html?embed=1&hostOrigin=<origin>`; manifest `/tetravox/manifest.json` `{name, version, protocol}`.
- **Scene** — Tetravox ViewSpec v2 with absolute same-origin `/api/files/raw/...` refs, empty fingerprints; server builds it from the existing ViewSpec in `tit/viewspec.py`.
- **FastSurfer in the image** — `FASTSURFER_HOME=/opt/fastsurfer` (git checkout at a pinned tag), checkpoints under `/opt/fastsurfer/checkpoints`, invoked by `tit.pre.fastsurfer` as `run_fastsurfer.sh --seg_only --no_cc --sid <id> --sd <derivatives/fastsurfer> --t1 <T1> --device cpu --threads N`; outputs `derivatives/fastsurfer/sub-<id>/mri/aparc.DKTatlas+aseg.deep.mgz` (+ `.nii.gz` copy) discovered by `VoxelAtlasManager`. Capability `fastsurfer: true` when the dir exists.
- **Capabilities** — `x11_display`, `freeview`, `gmsh`, `freesurfer` removed; `tetravox_embed {available, version, protocol}` and `fastsurfer` added.
- **Compose subset the app understands** — `services.<name>.{image, environment, volumes, ports, labels, healthcheck, command, working_dir, init}`, `networks`, `volumes`; `${VAR}` interpolation from the app's env map; anything else is a startup error naming the key.

## 2. Workstreams and owners (Phase A parallel; B after A; C integration)

| Lane | Model | Owns | Delivers |
|---|---|---|---|
| **W1 Tetravox Embed** (tetravox repo, `feat/embed`, worktree `/Users/idohaber/00_development/tetravox-wt-embed`) | Opus (resumed agent) | tetravox repo only | `packages/embed` (embed mode of the app renderer), protocol v1 + schema, `docs/EMBED.md`, example host, Playwright, `pack:embed` → `tetravox-embed-<ver>.tgz` with `manifest.json`, release asset step; commits on the branch, no push |
| **W2 Image** | Sonnet | `container/blueprint/Dockerfile.ti-toolbox` (new, based on main's `Dockerfile.simnibs`), `container/blueprint/entrypoint.ti-toolbox.sh`, `container/blueprint/build.sh`, `desktop/docker/docker-compose.v3.yml`, `dev/notes/image-size.md` | The image built locally (`--platform linux/amd64`): SimNIBS env + fastapi/uvicorn/pyyaml/psutil baked, FastSurfer + checkpoints, UI bundle, embed dir (build-arg tarball, placeholder allowed until W1 ships), no X11 libs, entrypoint runs `tit.server`; size before/after; smoke: health + `/tetravox/manifest.json` + `run_fastsurfer.sh --help`; compose v3 updated (no freesurfer service/volume, no X11 mounts, new image, healthcheck) |
| **W3a Server: Tetravox serving + scene v2** | Sonnet | `tit/server/**` (static.py, app.py CSP, settings.py, routes/{capabilities,viewers,files,catalog*}.py, routes/__init__), `tit/viewspec.py`, `contracts/**`, `tests/test_server*.py`, `tests/test_viewspec*.py`, `tests/test_files*.py`, `desktop/tests/mock-server/**`, `desktop/tests/fixtures/**`, `desktop/src/renderer/api/schema.d.ts` (gen:api) | `/tetravox/` static route with its own CSP (`script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:`) from `TIT_TETRAVOX_EMBED_DIR` (default `/opt/tetravox/embed`); capabilities per §1; scene = ViewSpec v2 (replace `TitScene`); Freeview/Gmsh launch routes + `_require_x11` deleted (ViewSpec builder kept); mock server serves a **fake embed** page (`desktop/tests/e2e/fixtures/fake-embed/`) speaking protocol v1 so the desktop e2e runs without the real bundle; contract gate green |
| **W3b Preprocessing: FastSurfer in, FreeSurfer out** | Opus | `tit/pre/**`, `tit/atlas/**` (except segstats.py/voxel.py internals already done), `tit/catalog.py`, `tit/jobs/plans.py`, `tit/jobs/kinds.py`, `tit/paths.py` (freesurfer listing → fastsurfer), `tit/gui/**` (delete the recon-all/subfield controls), `contracts/schema.json` fields for `PreprocessConfig` (report to W3a for the yaml), `tests/test_pre*.py`, `tests/test_catalog*.py`, `tests/test_atlas*.py`, `resources/atlas/*LUT*` if needed | `tit/pre/fastsurfer.py` runner + `PreprocessConfig.run_fastsurfer` replacing `run_recon_all`/subfields; DAG G2b = FastSurfer; `derivatives/fastsurfer` discovery in `VoxelAtlasManager`/catalog/subject presence chips (`raw/fastsurfer/m2m`); recon-all code, MATLAB-runtime subfields, FS license plumbing for the core removed; readers keep accepting legacy `derivatives/freesurfer` |
| **W4 Desktop: Docker via Engine API, X11 out** | Opus | `desktop/src/main/**` except `docker/` internals from N0.3 (extend allowed), `desktop/src/shared/compose.ts` + new `composeFile.ts`, `desktop/src/preload/**`, `desktop/src/shared/tit-bridge.d.ts`, `desktop/package.json` + lockfile (add `yaml`), `desktop/tests/unit/{compose,stack,docker-*,quitGate}*.test.ts`, `desktop/tests/e2e/{launcher,system}.spec.ts` + `fixtures/fake-docker.js` → `fake-engine-api.mjs` | `stack.ts` re-implemented on the Engine API: read compose v3 → pull (progress to the launcher) → network/volumes → create+start `tit` container with the app's env map → health → connect; logs/events stream; stop/remove on quit; `x11.ts`, X11 env/mounts, freesurfer service handling, `dockerCli.ts` CLI spawning deleted (only `docker context inspect` remains in `docker/discover.ts`); error UX for not-installed / not-running / socket permission / unsupported engine; launcher e2e against the fake Engine API |
| **W5 Desktop: Viewer on the embed, un-vendor** (Phase B) | Opus | `desktop/vendor/**` (delete), `desktop/scripts/vendor-tetravox.sh` (delete), `desktop/src/renderer/viewer/**`, `pages/viewer/**`, `pages/viewer-dev/**` (delete), `pages/results/**` ("Open in viewer"), `desktop/electron.vite.config.ts` (drop the tetravox chunk/optimizeDeps), `desktop/eslint.config.mjs`, `desktop/package.json` (remove `file:` deps + gl-matrix), `desktop/THIRD-PARTY-NOTICES.md`, `desktop/tests/e2e/viewer*.spec.ts`, `desktop/tests/unit/viewer-*.test.ts` | `TetravoxFrame.tsx` + `protocol.ts` (types from W1) + store with the same public surface; Viewer page = full-bleed iframe host + inspector (layers, cursor/space, layout, screenshot, save scene) + no-WebGL2 state; Results deep links; e2e against the fake embed, plus a real-embed spec gated on `TIT_TETRAVOX_EMBED_DIR` |
| **W6 Docs + CI** (Phase B) | Sonnet | `docs/**` wiki pages (installation, architecture, preprocessing, viewer), `README.md`, `.circleci/config.yml` (image build + smoke), `dev/update/**` (release: image tag), `CHANGELOG.md` | No-X11/no-FreeSurfer installation; migration note; CI builds the image and runs the container smoke |

**Phase C — integration (orchestrator + a 3-lens QA panel):** build the image with the real embed tarball; launch the Electron app offscreen against the stack via the Engine API; on sub-ernie: run a simulation, open it in the embedded viewer (probe assertions), run FastSurfer in the container, analyzer with the FastSurfer atlas; full gates (host pytest, container pytest, desktop typecheck/lint/vitest/build, `npm run e2e:quiet`); QA panel; fix pass.

## 2b. Tetravox Embed delivered (2026-09-03, lane W1)
Branch `feat/embed` in `/Users/idohaber/00_development/tetravox-wt-embed` (4 commits on top of tetravox main 0.3.4, HEAD `c56c3c8`, NOT pushed). Tarball to bake: `packages/embed/dist-pkg/tetravox-embed-0.3.4.tgz`, sha256 `e09a401b0c05da6f8d577095b94ac96f6d6d822db5e9db4466c3b321a5a70003`, 1,749,487 bytes; `manifest.json` `{"name":"@tetravox/embed","version":"0.3.4","protocol":1}`. Protocol v1 exactly as briefed (no deviations; additive extras `ready.caps.norm16`, `LoadedDataset.bytes`, `hostOrigin=*`). Facts for the host: relative `/api/files/raw/...` refs resolve against the embed's own `baseURI`, so no `baseUrl` is needed at `/tetravox/`; **dataset ids in `loaded` are NOT the ids sent** (Engine.load re-adds datasets) — map by name/order; a context-less embed still answers `hello` and reports `status: 'no-webgl2'`; the embed's own panels need ≥ 1000 px of iframe width. Serving: `application/wasm` on `assets/*.wasm`, no `X-Frame-Options: DENY`, no COOP/COEP, no Range needed.

## 3. Gates every lane must pass
Host `python3 -m pytest -q` (and the touched test modules inside `tit-v3-spike` for Linux), `black` on touched files, `dev/contracts_check.py` (W3a), `cd desktop && npm run typecheck && npm run lint && npx vitest run && npm run build`, and `npm run e2e:quiet` for anything that launches Electron. No monitor use: offscreen only.

## 4. Later (not in this program)
Native (no-Docker) mode; Podman/Colima support; Windows named-pipe verification; Intel Mac stays on this image under emulation; GPU FastSurfer build; ADMlib/MKL licensing review before any commercial distribution.

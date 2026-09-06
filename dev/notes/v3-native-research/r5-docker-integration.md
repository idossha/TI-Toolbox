# Lane R5 — Docker Integration Audit and Native-App Recommendation

Scope: what TI-Toolbox still needs Docker for once the core (tit, Tetravox, SimNIBS) is
compiled natively, and the most native way for an Electron+Python desktop app to talk to
Docker. All claims below are marked **VERIFIED** (I read the file/ran the command myself,
citation is `path:line` or a command+output) or **REPORTED** (a doc/README claims it, not
independently checked). Nothing in any repo was modified.

---

## 1. Current Docker usage — full audit

### 1.1 Legacy v2 launcher: `package/src/backend/docker-manager.js` (dockerode ^4.0.9)

**VERIFIED** — `package/package.json:35` pins `"dockerode": "^4.0.9"`, Electron `^28.0.0`
(`package/package.json:31`).

Every dockerode API call this file makes (`docker-manager.js`):

| Call | Line | Purpose |
|---|---|---|
| `new Docker({ socketPath })` / `new Docker({ host, port, protocol })` | `createDockerClient()` L76-107 | client construction; honors `DOCKER_HOST` (unix/npipe/tcp), else `/var/run/docker.sock` or `//./pipe/docker_engine` on win32 |
| `docker.version()` | `verifyDockerApi()` L123 | preflight: is the Engine API reachable |
| `docker.ping()` | `pingApi()` L167 | preflight |
| `docker.listContainers({all, filters:{name}})` | `getExistingContainers()` L174, `waitForContainer()` L309 | discover/poll `simnibs_container`/`freesurfer_container` |
| `container.stop({t:10})`, `container.remove({force:true})` | `cleanupExistingContainers()` L194-198 | force-kill any existing managed containers before every start (not attach-or-reuse — see §1.4 contrast) |
| `docker.listVolumes()`, `docker.getVolume(name).remove()` | `pruneOldVolumes()` L225-234 | GC stale versioned `ti-toolbox_freesurfer_data_*` volumes |
| `docker.getContainer('simnibs_container')`, `container.inspect()` | `launchGui()` L346-348 | verify the target container before exec |
| `container.exec({Cmd, AttachStdout, AttachStderr, Tty:true, WorkingDir, Env})` | `launchGui()` L384-392 | launch `simnibs_python -m tit.gui.main` **inside** the container |
| `exec.start({hijack:true, stdin:false})` | `launchGui()` L394 | the hijacked, bidirectional attach stream — this is dockerode's one genuinely hard-to-replicate feature (raw duplex stream over the multiplexed Docker attach protocol) |

Everything else in this file (`composeUp`/`composeDown`/`prepareStack`/`stop`) shells out to
the `docker compose` **CLI** via `execa`, not dockerode (`docker-manager.js:245-303`). So even
the legacy launcher is already a hybrid: dockerode only for container lifecycle/inspect/exec,
CLI for compose orchestration.

**Key fact for the "replace dockerode" question**: the *only* thing dockerode does in v2 that
a plain `docker compose ps`/`inspect` CLI call cannot equally do is `exec+hijack` (§1.4). v3
has already made this moot by dropping the in-container GUI exec entirely (see §1.2).

### 1.2 v3 desktop: `desktop/src/main/dockerCli.ts` + `stack.ts` — CLI only, no dockerode

**VERIFIED** — `desktop/package.json` has **no** `dockerode` dependency at all (`grep -n docker
desktop/package.json` → no hits; confirmed by reading the full file). `desktop/package.json:74`
pins Electron `44.0.0`.

`dockerCli.ts:1-6` states the design decision explicitly in its module docstring:

> "Docker discovery + compose lifecycle via the CLI (execa/execFile), never dockerode: the
> only thing the legacy launcher used the Engine API for was the GUI exec/hijack, which v3
> does not need (TODO §2.9)."

Concretely, v3's Docker surface is:

- `findDockerCommand()` (`dockerCli.ts:52-56`) — probes `DOCKER_CANDIDATES` (`/usr/local/bin/docker`,
  `/opt/homebrew/bin/docker`, `/usr/bin/docker`, Docker.app path), else bare `docker` on `PATH`.
  `TIT_DOCKER_BIN` env override exists solely for the E2E fake-docker harness (§1.6).
- `checkDocker()` (`dockerCli.ts:92-104`) — runs `docker context inspect --format
  '{{.Endpoints.docker.Host}}'` then `docker compose version`; classifies failure via
  `classifyDockerError` (`compose.ts:145-212`, five kinds: `daemon-not-running`,
  `socket-permission`, `wrong-context`, `image-offline`, `unknown`, each with an exact
  user-facing string).
- `runDockerStreaming()` (`dockerCli.ts:116-148`) — `execFile('docker', args)`, streams
  combined stdout/stderr line-by-line to a callback; used for both `up -d` and `down`.
- `composePs()` (`dockerCli.ts:182-187`) — `docker compose -p <project> ps --format json`,
  tolerant of both JSON-array and NDJSON output shapes (`parseComposePsOutput`, `dockerCli.ts:161-180`).
- `stack.ts` orchestrates: `checkDocker()` → attach-if-already-running (`isRunning()` via
  `composePs`, `stack.ts:194-197`) → else find a free port, generate a token, `ensureX11()`
  (`x11.ts`), `compose up -d` with progress parsed by `parsePullProgressLine`
  (`desktop/src/shared/pullProgress.ts:24-33`, ported from the v2 renderer's layer-tracking
  regex) → `waitForHealth()` on `/api/health`.
- `stackState.ts` persists `{projectName, hostProjectDir, port, token}` per project (0600,
  atomic write) so a later `stack.start` for the same directory **attaches** instead of
  force-removing — the exact "attach, don't kill" behavior v2's dockerode-based
  `cleanupExistingContainers()` (§1.1) does *not* have.

**No exec/hijack anywhere in v3** — Freeview/Gmsh are launched by `tit.server` itself (inside
the container, ordinary `subprocess`), not by Electron reaching in via `docker exec`. `x11.ts`
only sets up the *X11 socket/xhost grant* on the host side; the viewer program itself runs
server-side.

### 1.3 `docker-compose.v3.yml` — the actual container graph and its Docker-only reasons

**VERIFIED**, `desktop/docker/docker-compose.v3.yml:20-49`:

- `freesurfer` service: `idossha/ti-toolbox_freesurfer:v7.4.1`, `platform: linux/amd64`,
  named volume `freesurfer_data`.
- `tit` service: `idossha/simnibs:v2.4.0` (note: **pinned to v2.4.0 in this compose file**,
  not the v2.5.0 the task brief cites as current — a drift worth flagging separately), mounts:
  - `/tmp/.X11-unix:/tmp/.X11-unix:rw` — X11 socket, comment: "for Freeview/Gmsh viewer windows"
  - `${LOCAL_PROJECT_DIR}:/mnt/${PROJECT_DIR_NAME}` — the BIDS project
  - `${TIT_USER_CONFIG}:/root/.config/ti-toolbox`
  - **`/var/run/docker.sock:/var/run/docker.sock` — comment: "DooD for QSIPrep/QSIRecon"** — this is the load-bearing line for lane R5: the container needs the *host's* Docker socket to spawn QSIPrep/QSIRecon as sibling containers.
  - `${HOME}/.Xauthority:/root/.Xauthority:rw`
  - `${TIT_REPO_DIR}:/ti-toolbox` (dev image only)

So today, one container (`tit`) is handed the host Docker socket so that Python code running
*inside* it can launch further containers next to itself (Docker-outside-of-Docker, DooD) —
this is architecturally the same pattern as v2, just moved from Electron-orchestrated dockerode
calls to Python-orchestrated CLI calls happening one container hop further in.

### 1.4 In-container DooD: `tit/pre/qsi/*.py` — how QSIPrep/QSIRecon actually run

**VERIFIED**, no `dockerode` or Docker Python SDK involved at all — pure `subprocess` calls to
the `docker` CLI binary that DooD makes available inside the `tit` container via the mounted
socket:

- `tit/pre/qsi/utils.py:118-127` `check_image_exists()` → `subprocess.run(["docker", "image",
  "inspect", f"{image}:{tag}"])`.
- `tit/pre/qsi/utils.py:130-173` `pull_image_if_needed()` → `subprocess.run(["docker", "pull",
  full_image], timeout=1800)` — **no progress streaming at all**: this call blocks up to 30
  minutes and only reports success/failure at the end, unlike the v3 desktop's own
  `runDockerStreaming`/`parsePullProgressLine` pull-progress UI for the *outer* `tit` image.
  A user waiting on a first QSIPrep pull (image is large — PennLINC images run several GB) gets
  no incremental feedback today.
- `tit/pre/qsi/utils.py:176-217` `validate_dood_environment()` → `shutil.which("docker")`,
  checks `LOCAL_PROJECT_DIR` env var is set (`ENV_LOCAL_PROJECT_DIR = "LOCAL_PROJECT_DIR"`,
  `tit/constants.py:713`), then `subprocess.run(["docker", "info"], timeout=15)`; for
  `require_gpu=True` greps `"nvidia"` out of `docker info` text.
- `tit/pre/qsi/docker_builder.py:135-233` `build_qsiprep_cmd()` / `:235-344`
  `build_qsirecon_cmd()` — hand-build a full `docker run --rm --platform linux/amd64 --name
  ... --cpus N --memory Ng -e ... -v host:container[:ro] image args...` argv list as
  `list[str]`. Resource limits (`get_inherited_dood_resources()`,
  `tit/pre/qsi/utils.py:799-818`) are derived by reading the **current container's own**
  cgroup v1/v2 files (`/sys/fs/cgroup/cpuset.cpus.effective`, `cpu.max`,
  `memory.max`/`memory.limit_in_bytes`, `/proc/meminfo`) — i.e. the DooD sibling is sized to
  match whatever cgroup limits Docker Desktop/the orchestrator gave the *parent* `tit`
  container, since the sibling itself, spawned via the host socket, is a **peer** of `tit`, not
  a cgroup child of it, and would otherwise see the full host's resources.
- Host-path translation: `resolve_host_project_path()` / `get_host_project_dir()`
  (`tit/pre/qsi/utils.py:31-99`) rewrite the *container-visible* `/mnt/<project>` path back to
  `LOCAL_PROJECT_DIR` (the real host path) before building `-v` mounts for the sibling — a DooD
  sibling's bind mounts are always resolved by the **host** Docker daemon against **host**
  paths, never the calling container's paths, so this translation is required correctness, not
  cosmetic.
- `tit/pre/qsi/qsiprep.py:75-219` `run_qsiprep()` / `tit/pre/qsi/qsirecon.py:27-192`
  `run_qsirecon()` — validate DooD env + BIDS DWI + `TotalReadoutTime` sidecar → build cmd →
  `pull_image_if_needed()` → `runner.run(cmd, logger=logger)` where `runner` is
  `tit.pre.utils.CommandRunner` (`tit/pre/utils.py:378-497`), the same
  cancellable-subprocess-with-line-streaming wrapper used for every other `tit.pre` external
  tool call (dcm2niix, recon-all, etc.) — QSIPrep/QSIRecon containers are, from the code's point
  of view, just another external command, indistinguishable from a native binary invocation
  except that the argv happens to start with `docker run`.

**Finding — the job-cancel/container label is dead code today.** `tit/jobs/runner.py:223-235`
`stop_docker_siblings(job_id)` filters `docker ps -q --filter
label=tit.job_id={job_id}` and its docstring (`runner.py:224-227`) says *"QSIPrep/QSIRecon's
DooD builders add this label"*. I grepped the whole repo for `tit.job_id` (`rg -n "tit\.job_id"
tit/`) and the **only** two hits are the two lines inside `runner.py` itself (the docstring and
the filter string) — `docker_builder.py`'s `build_qsiprep_cmd`/`build_qsirecon_cmd` (read in
full above, lines 135-344) never emit a `--label` flag. So `stop_docker_siblings` currently
always finds zero matching containers for QSIPrep/QSIRecon; cancelling such a job relies
entirely on `terminate_tree()` SIGTERM-ing the *foreground* `docker run` client process
(`docker_builder.py`'s command has no `-d`/detach, so it runs attached — a SIGTERM to the docker
CLI client conventionally does forward to the container and triggers its shutdown, but this is
CLI behavior being relied on implicitly, not the explicit label-based mechanism the docstring
describes). This is a real gap to fix regardless of the native-app question, and doubly relevant
here: any new container-job design (§4) should either implement the label for real or drop the
docstring's claim.

### 1.5 `tit/server/routes/capabilities.py` — `docker_socket` capability

**VERIFIED**, `capabilities.py:16,38-46`: `probe_capabilities()` sets `docker_socket =
os.path.exists("/var/run/docker.sock")` — a pure filesystem-existence check, **not** a
liveness/reachability probe (contrast with `tit/pre/qsi/utils.py`'s `docker info` call, which
*does* verify the daemon actually answers). The capability is surfaced in the generated OpenAPI
type (`desktop/src/renderer/api/schema.d.ts:2578: docker_socket: boolean;`) but I grepped the
entire renderer tree (`grep -rn "docker_socket\|dockerSocket" desktop/src/renderer --include=
"*.tsx" --include="*.ts"`, excluding the generated schema file) and found **zero** consumers —
no UI currently greys out QSIPrep/QSIRecon controls (or anything else) based on this
capability. It exists in the contract but nothing reads it yet.

### 1.6 Test harness: `desktop/tests/e2e/fixtures/fake-docker.js`

**VERIFIED**, read in full (176 lines). This fakes the **`docker` CLI**, not the Engine API: it
is installed as a stand-in binary (via `TIT_DOCKER_BIN`/PATH, matching `dockerCli.ts:53`'s
override hook) and answers exactly the five subcommand shapes `dockerCli.ts`/`stack.ts` issue —
`context inspect`, `compose version`, `compose ... up -d`, `compose ... ps --format json`,
`compose ... down` — with canned stdout. For `up -d` it spawns a **separate detached Node
process** (re-invoking itself with `--serve-fake-server`) that runs a real tiny HTTP server on
`TIT_SERVER_PORT` answering `/api/health`, `/api/version`, `/api/jobs`, `/auth/session` the way
`tit.server` does, so `stack.start`'s health/token/session flow succeeds with no real Docker or
SimNIBS present. State (`running`/`serverPid`/`port`) persists as JSON under
`TIT_FAKE_DOCKER_STATE_DIR` so `down` can find the pid to `SIGTERM`.

**Can it fake the Engine API instead of the CLI?** Not without rework, and I'd argue it
shouldn't try to — see §7.

---

## 2. What remains Docker-only after the native core lands

Given the mounts/images above, the pieces that cannot become "just a bundled native binary"
without a much larger effort than this program's scope:

1. **QSIPrep + QSIRecon** (`pennlinc/qsiprep:26.0.0`, `pennlinc/qsirecon:26.0.0`,
   `docker_builder.py:149,251`) — Linux-only container images (built on a Debian/Ubuntu base
   with the full nipype/ANTs/MRtrix/DSI-Studio/FSL toolchain), tens of GB combined
   (**REPORTED** — the maintainer's brief states ~30 GB; I did not independently measure image
   size, `docker image inspect` was not run against these tags in this session). Nothing in
   PennLINC's distribution ships a native macOS/Windows build; realistically these stay
   containerized indefinitely, or become an optional remote/cluster job kind rather than a
   local Docker job kind. This is a "Docker-only workload," not a "Docker-implementation-detail"
   — it is only relevant to R5 in that it justifies why the app still needs Docker access at
   all, and needs a way to run and stream logs from an arbitrary sibling container even after
   its own SimNIBS/FreeSurfer/GUI stack goes native.
2. **FreeSurfer** (`idossha/ti-toolbox_freesurfer:v7.4.1`, ~67 GB per the task brief) — *if*
   kept as a legacy/optional path once a native parcellation replacement (FastSurfer or
   similar, out of scope for R5) lands. Whether FreeSurfer itself stays containerized is a
   product decision for another lane; from R5's angle, as long as it exists as a container it
   needs the same lifecycle primitives as QSIPrep/QSIRecon.
3. **A future FastSurfer GPU image**, if the parcellation replacement is itself shipped as a
   container rather than compiled in (a real possibility if FastSurfer's own GPU/CUDA runtime
   dependency chain is heavy) — same primitives again.

Everything else the current stack uses Docker for (running `tit.server` itself, running
SimNIBS simulations, the GUI) is exactly what the rest of this native-app program (other lanes)
is proposing to make native — once that lands, Docker is no longer needed for *those*
workloads, only for the three above.

---

## 3. Option evaluation

### (a) Docker Engine API directly over the socket/pipe, small typed client

**Feasible, and this is what I recommend for the pieces that stay containerized.** Node's
`http.request({socketPath, path, method, headers})` already speaks HTTP/1.1 over a Unix domain
socket without any extra dependency, and the same `net`/`http` stack supports connecting to a
Windows named pipe path — this is confirmed both by Node's own long-standing named-pipe server
support and by the fact that `dockerode`'s own transport layer (`docker-modem`) is built on
exactly this mechanism (Node `http.request` + `socketPath`) rather than anything more exotic
(cross-checked via `gh api repos/apocas/dockerode` and web search on
`http.request socketPath` npipe behavior — dockerode is the reference implementation of "raw
HTTP over the Docker socket in Node," which is direct evidence the mechanism works, since
dockerode is what v2 already ran in production).

Docker Engine API facts (**REPORTED**, from `docs.docker.com/reference/api/engine/`, fetched
this session):
- Current stable API version is **1.55**, shipped by Docker 29.7/29.6.
- Minimum floor for modern Docker (29.x) is **API 1.40**; older Docker installs go down to
  1.12 (Docker 24.0).
- Client/daemon negotiate the highest mutually-supported version automatically; `Docker-API-Version`
  in requests can pin a specific version, or `DOCKER_API_VERSION` env var overrides.
- **VERIFIED** independently: the `docker` CLI inside the running `tit-v3-spike` spike container
  reports `Docker version 29.7.2, build a7dcaa6` (`docker exec tit-v3-spike docker --version`)
  — consistent with the 1.5x-series API being what the current fleet actually speaks.

Endpoints a minimal client needs (standard REST paths under `/v1.4x/...`, unversioned prefix
also accepted by the daemon):
- `GET /version`, `GET /info`, `GET /_ping` — capability/liveness probes (replaces
  `checkDocker()`'s `docker context inspect` + `compose version` shell-outs, and
  `validate_dood_environment()`'s `docker info` shell-out).
- `POST /images/create?fromImage=...&tag=...` — pull, **streams** newline-delimited JSON
  progress objects (`{status, progressDetail:{current,total}, id}`) natively; this is a strict
  upgrade over both the current line-regex parsing in `pullProgress.ts` (built for
  human-readable CLI text) and the current QSI-side `pull_image_if_needed()`'s "block 30
  minutes, no progress at all" behavior (§1.4).
- `POST /containers/create`, `POST /containers/{id}/start`, `POST /containers/{id}/wait`,
  `GET /containers/{id}/logs?follow=true&stdout=true&stderr=true` (chunked, Docker's own 8-byte
  stream-multiplexing framing when not a TTY), `POST /containers/{id}/stop`,
  `POST /containers/{id}/kill` — direct replacements for a `docker run ...` argv, with an
  actual container ID/handle returned immediately instead of a foreground CLI process whose pid
  is the only handle (as today).
- `POST /containers/{id}/exec` + `POST /exec/{id}/start` (hijacked) — only needed if the app
  ever again wants to exec *into* a running container; **not needed** by v3's own architecture
  (§1.2 confirms v3 dropped this), only potentially useful for a future interactive
  debug/shell feature.
- `GET /events?filters=...` — real-time container lifecycle events (`start`, `die`, `oom`),
  which would let the job runner know a QSIPrep container died without polling.
- `GET /system/df` — disk usage; useful for a "Docker is eating N GB, want to prune?" settings
  panel, not used by anything today.

**Versioning stance**: pin a `Docker-API-Version` header no lower than what QSIPrep/QSIRecon's
own images assume compatible daemons run (effectively "any Docker released in the last several
years," since these workloads already require Docker Desktop or a modern engine for
`--platform linux/amd64` emulation on Apple Silicon) — practically, targeting **API ≥ 1.41**
(Docker ≥ 20.10, released 2020) is a safe, generous floor; do not chase 1.55 exactly, since
version negotiation degrades gracefully.

### (b) dockerode 4.x

**REPORTED/VERIFIED maintenance state** (checked via `gh api repos/apocas/dockerode` and
`registry.npmjs.org/dockerode` this session): actively maintained — `pushed_at:
2026-09-03T00:11:41Z` (today), 4,945 GitHub stars, 27 open issues, not archived. Latest release
is **v5.0.1** (published 2026-06-24), with v4.0.10-4.0.12 patch releases through 2026-03. The
last several commits on `main` (checked 2026-08-05 and earlier) are dependency-bump PRs
(`protobufjs`, `js-yaml`) via dependabot, not feature work — consistent with a stable,
low-churn library rather than one under active feature development. It "adds" over raw HTTP:
typed convenience wrappers (`docker.getContainer(id).stop()` etc.), the `docker-modem` layer
that already handles socket/npipe/TCP+TLS transport and stream demultiplexing, and
Promise/callback dual API.

Given v3 already deliberately dropped dockerode in favor of CLI-spawn (`dockerCli.ts:1-6`'s
explicit docstring reasoning — §1.2), re-introducing it now only to replace the CLI-spawn
approach would be a partial step: dockerode still shells out to nothing (it *is* the raw-API
client, just pre-built), but adopting it means taking on its full dependency surface
(`docker-modem`, `docker-parse-image`, `tar-fs`, `protobufjs` — this last one exists only for
buildkit/BuildKit-session support, dead weight for a client that only ever *runs* pre-built
images and never builds one) for a feature set (build, swarm, secrets, networks-as-objects)
this program does not need. A **hand-rolled client scoped to exactly the ~10 endpoints in
§3(a)** is smaller, has zero runtime dependencies, and is trivially portable to the Python side
(§5) in a way "use dockerode" is not (dockerode is Node-only).

### (c) Docker Desktop/Compose v2 CLI shelling (current v3 approach)

Pros (all **VERIFIED** from reading the code): gets `docker compose`'s dependency-graph
semantics essentially for free (`depends_on`, named volumes, network creation) — the exact
thing `docker-compose.v3.yml` uses for `freesurfer`→`tit`'s `depends_on`; requires no new
runtime dependency; already ships working error classification
(`classifyDockerError`, `compose.ts:145-212`) and a working pull-progress parser
(`pullProgress.ts`) built and presumably tuned against real `docker compose up` output.

Cons: line-oriented text parsing is inherently fragile across Docker/Compose versions and
locales (the NDJSON-vs-array tolerance already needed in `parseComposePsOutput`,
`dockerCli.ts:161-180`, is a symptom of this); no structured events (must poll `compose ps`);
requires the `docker` CLI binary to be discoverable and correctly resolve `compose` as a
plugin, which is an extra moving part beyond "a socket exists" — `checkDocker()`'s two-step
probe (`context inspect` then `compose version`) exists precisely because those are two
independently-failing things.

Given only two services and no build step in `docker-compose.v3.yml`, compose's marginal value
over "the client itself creates/starts two containers with explicit `depends_on` ordering and a
shared network" is small — a hand-rolled Engine-API client can trivially reproduce this exact
two-service graph (§4's `runJobContainer` plus one `docker network create`), and gains
structured events/logs in return. I would keep the CLI path only as documented fallback/parity
tests, not as the primary mechanism.

### (d) Podman/Colima/Rancher/OrbStack compatibility

The Engine-API approach in (a) is what makes this tractable at all: Podman, Colima, and
OrbStack all speak the same Docker Engine REST API (Podman via its Docker-compatibility socket,
Colima and OrbStack by running an actual Docker daemon or an API-compatible shim) over a
different socket path, so a client written against the API rather than the CLI's text output
only needs correct **socket discovery**, not per-tool special-casing:

- macOS/Linux, `DOCKER_HOST` unset: **REPORTED** (web search, not independently verified on
  this machine) default socket candidates, in rough precedence order a client should try:
  `~/.docker/run/docker.sock` (Docker Desktop's own default context on recent versions),
  `/var/run/docker.sock` (classic default / Docker Desktop's legacy symlink / Linux native
  Docker), `~/.colima/default/docker.sock` (Colima, non-default profile is
  `~/.colima/<profile>/docker.sock`), OrbStack (**REPORTED**, not verified — OrbStack's own
  docs describe it as a drop-in Docker Desktop replacement and its socket is typically
  `~/.orbstack/run/docker.sock` per OrbStack's documentation, though this specific path was not
  independently fetched and confirmed in this session).
- **The robust way to find the right one, on every platform, is `docker context inspect
  --format '{{.Endpoints.docker.Host}}'`** (or, without shelling out at all, reading
  `~/.docker/config.json`'s `currentContext` and the corresponding
  `~/.docker/contexts/meta/<sha256 of context name>/meta.json`) — this is exactly what
  `dockerCli.ts:92-104`'s `checkDocker()` already does today, and it is the one mechanism that
  transparently follows whatever the user (or Colima's/Podman's/OrbStack's own installer) has
  set as the active context, without the client hard-coding a candidate list. **Recommendation**:
  keep `docker context inspect` (or the equivalent config-file read) as the *discovery* step —
  it costs one CLI shell-out at startup, which is fine — but use the resulting socket path to
  drive the typed Engine-API client for every subsequent call, instead of shelling out to
  `docker` for each one as `dockerCli.ts`/`stack.ts`/`tit/pre/qsi/*` do today. `DOCKER_HOST`
  (`unix://`, `npipe://`, `tcp://` with optional TLS context) still needs to be honored first
  when set, matching `docker-manager.js:88-107`'s existing `parseDockerHost()` logic almost
  verbatim.
- Windows: `npipe:////./pipe/docker_engine` is Docker Desktop's default; **REPORTED** Podman on
  Windows also listens on this same pipe name so `DOCKER_HOST` frequently doesn't need setting
  for Podman Desktop users either (per Podman Desktop's own migration docs, fetched via search
  this session, not independently confirmed against a running Podman-on-Windows instance).

None of this requires per-runtime special-casing in the client itself once it's talking the
Engine API over a discovered socket — compatibility with Podman/Colima/OrbStack is a property
of *using the standard API* rather than *shelling out to the `docker` binary and parsing its
text*, which is the strongest argument for (a) over (c).

### (e) Libraries that embed the engine

None realistic, confirmed by the shape of the problem, not by an exhaustive library search: an
embeddable Docker/OCI engine would still need Linux containerization primitives (namespaces,
cgroups) unavailable on macOS/Windows kernels, so on those platforms it would itself have to run
inside a Linux VM — i.e. it would *be* Docker Desktop/Colima/Podman-machine, not a replacement
for needing one of them. This is architecturally why "just embed the engine" collapses back
into option (d)'s socket-discovery problem rather than eliminating it.

---

## 4. Recommended minimal typed Engine-API client — interface sketch

A single small module (no new production dependency beyond Node's stdlib `http`/`net`), roughly:

```ts
// desktop/src/main/dockerEngine.ts (sketch — names indicative, not final)

export interface DockerConnection {
  kind: "unix" | "npipe" | "tcp";
  socketPath?: string;      // unix/npipe
  host?: string; port?: number; tls?: TlsOptions; // tcp
}

/** DOCKER_HOST if set, else `docker context inspect` (or its config-file read), else
 *  platform-default candidate list. Mirrors dockerCli.ts's checkDocker() discovery but
 *  returns a connection descriptor instead of a boolean. */
export async function detect(): Promise<DockerConnection | { available: false; kind: DockerErrorKind; message: string }>;

export interface PullProgressEvent { id?: string; status: string; current?: number; total?: number; }

/** POST /images/create — streams NDJSON progress, resolves when the pull finishes. */
export function pullImage(conn: DockerConnection, image: string, tag: string,
  onProgress: (e: PullProgressEvent) => void): Promise<void>;

export interface RunJobContainerOpts {
  image: string; name: string; cmd: string[];
  mounts: { hostPath: string; containerPath: string; readOnly?: boolean }[];
  env: Record<string, string>;
  cpus?: number; memoryGb?: number; gpus?: boolean; platform?: string; // "linux/amd64"
  labels: Record<string, string>;   // always includes tit.job_id — see §1.4 finding
}
export interface RunningJobContainer {
  id: string;
  logs(): AsyncIterable<{ stream: "stdout" | "stderr"; line: string }>;
  wait(): Promise<{ exitCode: number }>;
  stop(graceSeconds?: number): Promise<void>;
  kill(): Promise<void>;
}
/** create + start; returns a handle immediately (unlike today's foreground `docker run`,
 *  whose only handle is a subprocess pid). */
export function runJobContainer(conn: DockerConnection, opts: RunJobContainerOpts): Promise<RunningJobContainer>;

export function events(conn: DockerConnection, filters: Record<string, string[]>):
  AsyncIterable<{ type: string; action: string; id: string }>;   // GET /events

export function info(conn: DockerConnection): Promise<{ serverVersion: string; apiVersion: string }>;  // GET /version, /info
```

This directly replaces: `checkDocker()`, `runDockerStreaming()`'s `up`/`down` calls (for the
two-service stack, `runJobContainer` × 2 with an explicit `depends_on` wait, or one
`docker network create` + two containers), `composePs()` (poll `GET
/containers/json?filters={"name":[...]}`instead), and on the Python side, every
`subprocess.run(["docker", ...])` call in `tit/pre/qsi/*.py` (§1.4).

---

## 5. Mapping onto `tit.jobs` — a `container` job kind, and which side should own it

**VERIFIED** the existing extension point: `tit/jobs/runner.py:66-93`'s `Runner` ABC is
*already* designed for exactly this kind of substitution — its own docstring
(`runner.py:1-10`) says: *"`Runner` is deliberately narrow (`spawn` only) so a future
`SbatchRunner` (3.1, HPC) can drop in."* `LocalPopenRunner.spawn()` returns an
`asyncio.subprocess.Process`; a hypothetical `ContainerRunner.spawn()` would need to return
something that fulfills the same downstream contract everything else in `manager.py`
depends on: a `pid` the status record can store (`status.pid`/`status.create_time`,
consumed by `is_alive()`/`terminate_tree()`, `runner.py:148-221`), so that reattach-after-restart
keeps working unchanged.

Two ways to satisfy that, and which I'd pick:

**Recommended: Python owns it, via a `container` job `kind`, implemented as a thin subprocess
wrapping the container as today (`docker run` in the foreground, no `-d`) — but with the
`--label tit.job_id=<id>` gap (§1.4) actually fixed, and switched from CLI-argv-building
(`docker_builder.py`) to the same typed Engine-API client, ported to Python, that Electron uses.**
Rationale:
- The `container` workloads (QSIPrep/QSIRecon, possibly FreeSurfer/FastSurfer) are today
  triggered *from inside* `tit.pre`, as steps of a preprocessing job the `LocalPopenRunner`
  already owns end-to-end — moving container orchestration to the Electron main process would
  mean either (a) `tit.server`'s job runner calling back out to Electron mid-job to spawn a
  sibling container (a new IPC surface with no precedent in this architecture — `tit.server` is
  designed to run headless, e.g. under JupyterHub per `project_jupyterhub_hosting.md`, where
  there *is no* Electron main process to call back into), or (b) keeping the DooD pattern
  exactly as today but with a proper client instead of argv-building + `subprocess`. (b) is a
  strict improvement with no architectural risk.
- A Python client over the same Unix socket needs no `docker` Python SDK dependency at all:
  Python's stdlib `http.client.HTTPConnection` can be subclassed to `connect()` over a
  `socket.AF_UNIX` socket in ~15 lines (a well-known, dependency-free pattern), which matches
  the "raw HTTP over socket" approach in (a) rather than adding the `docker` PyPI package
  (**VERIFIED** current: v7.2.0, `requires_python>=3.8`, last upload 2026-07-09; GitHub
  `docker/docker-py` `pushed_at: 2026-08-31`, 7,212 stars, 569 open issues — actively
  maintained but noticeably higher open-issue count than dockerode's 27, suggesting slower
  triage). **VERIFIED** the `docker` package is **not** currently installed in the
  `idossha/simnibs:v2.5.0` image (`docker exec tit-v3-spike simnibs_python -c "import docker"`
  → `ModuleNotFoundError`), while the `docker` **CLI** binary is present (`/usr/bin/docker`,
  v29.7.2) — i.e. today's DooD pattern already depends on the CLI being baked into the image;
  switching to a raw-socket HTTP client removes that dependency (no new package needed, and
  one less binary the image has to ship), while switching to the `docker` SDK would *add* one.
  I'd recommend the raw-socket approach for parity with the Node side and to avoid growing the
  19 GB image further.
- Windows named-pipe DooD is moot: QSIPrep/QSIRecon only ever run *inside* the Linux `tit`
  container (`docker-compose.v3.yml`'s socket mount is `/var/run/docker.sock`, a Unix path,
  regardless of the *host* OS) — the Python client only ever needs the Unix-socket transport,
  never npipe. npipe only matters to the **Electron** client (§4), which runs on the actual host
  OS.
- This also means the Node Engine-API client (§4) and the Python one share almost no code
  (different languages) but should share the *same interface shape* (`pullImage`,
  `runJobContainer`, `stop`/`kill`) so the two implementations stay conceptually
  interchangeable and either could, in principle, be swapped for the other if the DooD pattern
  is ever replaced with "Electron spawns QSIPrep directly, bypassing the inner container" (a
  bigger architectural change, out of scope here, but one this interface choice doesn't
  foreclose).

**Where Electron's own Engine-API client (§4) is actually used**, then, is narrower than "every
container the app runs": it's the **outer** `tit`/`freesurfer` compose-equivalent stack
(`stack.ts`'s job today) — i.e. replacing the CLI-spawn compose orchestration, not the inner
DooD QSIPrep/QSIRecon spawning, which stays a Python-owned `tit.jobs` concern either way.

---

## 6. Error UX

The existing `classifyDockerError` taxonomy (`compose.ts:133-212`) is already close to right
and should carry over to an Engine-API client with the *symptoms* re-derived from HTTP-level
signals instead of stderr text-matching, which is materially more reliable:

| Kind | Today (text match on stderr) | Engine-API equivalent |
|---|---|---|
| `daemon-not-running` | grep "cannot connect to the docker daemon" | `ECONNREFUSED`/`ENOENT` connecting to the socket path at all — no HTTP request even completes |
| `socket-permission` | grep "permission denied" + "docker.sock" | `EACCES` connecting to the socket (Linux: user not in `docker` group) |
| `wrong-context` | grep "context" + "not found"/"unreachable" | discovery step (`docker context inspect`, still shelled out per §3(d)) fails, or the resolved socket path doesn't exist |
| `image-offline` | grep "no such host"/"manifest unknown" | `POST /images/create` returns HTTP 404 (unknown repository/tag) vs. the request never completing (DNS/network failure) — an HTTP status code is a strictly more reliable signal than grepping the registry's own error prose, which changes across registries and Docker versions |
| `unknown` | last non-empty stderr line | HTTP status + JSON `{"message": "..."}` body Docker always returns on error — again more structured than free text |

"Docker not installed" specifically: today this is indistinguishable from "not running" once
`findDockerCommand()`'s fallback list is exhausted and it's just hoping `docker` is on `PATH`
(`dockerCli.ts:52-56`) — an Engine-API client should surface this as its own distinct state
(no socket at any known path, and no `docker` binary found for the one shell-out that discovery
still needs) rather than folding it into `daemon-not-running`, since the remediation copy is
different ("install Docker Desktop" vs. "start Docker Desktop").

---

## 7. Tests — extending `fake-docker.js`

**Recommendation: build a second, parallel fixture — a fake Engine-API HTTP server listening
on a Unix socket — rather than trying to make `fake-docker.js` itself answer Engine-API
requests.** Reasons:
- `fake-docker.js` earns its keep specifically by masquerading as the `docker` **binary** on
  `PATH`/`TIT_DOCKER_BIN` (§1.6) — that trick has no equivalent for a socket-based client, which
  never invokes a binary at all; there is nothing to intercept via `PATH`.
- The natural fake for an Engine-API client is a tiny real HTTP server bound to a Unix socket
  path the test points the client at via the same discovery override the real client would
  honor (`DOCKER_HOST=unix:///tmp/.../fake-engine.sock`), answering the handful of endpoints in
  §3(a) with canned JSON/NDJSON — genuinely simpler to write than `fake-docker.js`'s current
  CLI-arg-shape matching, since HTTP methods+paths are a cleaner surface than argv parsing, and
  it can reuse the *same* `--serve-fake-server`-style detached-process pattern
  (`fake-docker.js:57-99`) already proven to work for standing in as "the container."
- Both fixtures can coexist: keep `fake-docker.js` as-is for exercising `checkDocker()`'s
  `docker context inspect`/`compose version` discovery shell-outs (§3(d) keeps these as the
  discovery step even under the Engine-API recommendation) and compose-CLI parity/fallback
  tests; add a new `fake-engine-api.js` (or similar) for everything that moves onto the typed
  client (`runJobContainer`, `pullImage`, `events`). This mirrors the actual production split:
  one shell-out for discovery, then direct API calls for everything else.

---

## 8. Summary verdict

Realistic, and the two v3 codebases already point the same direction: v3 desktop **already
dropped dockerode** for CLI-spawn (§1.2, a deliberate choice recorded in `dockerCli.ts`'s own
docstring), and the in-container DooD side (§1.4) never used anything but `subprocess` +
`docker` CLI to begin with. The next step is not "add dockerode back" (option b) nor "keep
shelling out to `docker compose`/`docker run` forever" (option c, current state) but **replace
both CLI-spawn surfaces with one small, dependency-free, typed Engine-API client per language**
(§4), talking directly to the socket/pipe that `docker context inspect` (or Podman/Colima/
OrbStack's own context) resolves — which is simultaneously the most "native" integration
available (no dockerode, no CLI subprocess-and-parse for anything but startup discovery) and
the one that gets Podman/Colima/OrbStack compatibility "for free," since compatibility with all
of them is a property of speaking the standard REST API rather than parsing any one vendor's
CLI text output. QSIPrep/QSIRecon (and FreeSurfer/FastSurfer, if they stay containerized) remain
Docker-only workloads under this design — nothing here removes Docker as a runtime dependency
for the app as a whole, only removes dockerode/CLI-parsing as the *mechanism* by which the app
talks to it.

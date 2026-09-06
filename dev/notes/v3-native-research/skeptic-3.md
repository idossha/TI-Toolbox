# Skeptic 3 — Docker/QSIPrep/long-running-jobs lens

Reviewer role: systems engineer responsible for Docker/QSIPrep/long-running jobs — Engine
API over socket on 3 OSes, socket permissions, Podman/Colima, streaming, process trees, what
still cannot run natively. All six reports read in full
(`r1-simnibs-packaging.md` … `r6-native-deps-audit.md`). No repository file was modified in
this review (confirmed `git status --short` in the worktree shows only pre-existing local WIP
from before this session — nothing added by me). Every claim below carries a citation I
personally checked this session: a `file:line` I read, a command I ran with its output shown,
or a URL I fetched myself.

---

## Method

I re-derived the ten claims most load-bearing for the maintainer's three asks (native
Electron app with SimNIBS+Tetravox, no X11/FreeSurfer/Gmsh, on 3 OSes; a FreeSurfer-free
parcellation; a "more native" Docker integration), weighted toward my assigned lens
(container lifecycle, process management, cross-runtime Docker compatibility). For each I ran
an independent check — a live `curl`/`gh api`/PyPI JSON fetch, a `grep`/`Read` against the
actual worktree file, or a fetch of a primary doc (Python's own signal docs, Docker's own API
docs, FastSurfer's own INSTALL.md, Podman's own man pages). Default posture: refute unless my
own check agrees.

---

## Claim-by-claim

### 1. UPHELD — v3 desktop dropped dockerode; CLI-spawn (`dockerCli.ts`) is what's there today

**Source**: R5 §1.2, R6 §5. **My check**: `grep -rn "dockerode" desktop/package.json
desktop/src` → zero hits except the *word* "dockerode" inside `dockerCli.ts`'s own docstring
explaining why it isn't used. Read `desktop/src/main/dockerCli.ts:1-20` myself — confirms the
CLI-only (`execFile`) design. **Nuance not to lose**: this upholds the narrow factual claim
("dockerode is gone"), but R5's own final recommendation (§8) is that this CLI-spawn state is
*not* the end state — it argues CLI-spawn should itself be replaced by a hand-rolled Engine-API
client. Reading R5/R6 quickly could leave the impression "the dockerode question is solved";
what's actually true is "dockerode is gone, but so is any typed API client — today's state is
CLI-text-parsing, one rung better than dockerode, not the target architecture."

### 2. UPHELD — the `docker.sock` DooD mount is the load-bearing reason a native app still needs Docker at all

**Source**: R5 §1.3. **My check**: read `desktop/docker/docker-compose.v3.yml` in full myself
— line-for-line confirms `- /var/run/docker.sock:/var/run/docker.sock # DooD for
QSIPrep/QSIRecon` on the `tit` service, plus confirms the file is pinned to `idossha/simnibs:v2.4.0`
(not v2.5.0 as the task brief states — R5's drift flag is independently confirmed).

### 3. UPHELD — `stop_docker_siblings()` is dead code today; QSIPrep/QSIRecon job-cancel has no real container handle

**Source**: R5 §1.4. **My check**: `grep -n "label" tit/pre/qsi/docker_builder.py` returns
only `--participant-label` (QSIPrep's own BIDS arg, unrelated to Docker labels) — **zero**
`--label` flags are ever built into the `docker run` argv. `grep -rn "tit\.job_id" tit/`
confirms the string exists in exactly two places, both inside `runner.py:224-235`'s own
docstring/filter, never emitted by the builder. This means `stop_docker_siblings(job_id)`
filters `docker ps -q --filter label=tit.job_id=<id>` and will **always return zero matches**
for a QSIPrep/QSIRecon job — cancellation for that job kind depends entirely on
`terminate_tree()` SIGTERM-ing the foreground `docker run` client process and hoping the CLI
forwards it to the container (undocumented, version-dependent CLI behavior, not a guaranteed
contract). This is a concrete, currently-shipping gap directly in my lens (long-running job
cancellation) that any "more native" Docker redesign needs to actually close, not just port
forward.

### 4. UPHELD, upgraded from REPORTED to VERIFIED — Windows job-kill crashes on `signal.SIGKILL`

**Source**: R6 §2a, self-rated "REPORTED but high-confidence" (could not run a Windows
interpreter). **My check**: fetched `docs.python.org/3/library/signal.html` directly. Primary
source, quoted verbatim: *"signal.SIGKILL — Kill signal. It cannot be caught, blocked, or
ignored. Availability: Unix."* and *"On Windows, signal() can only be called with SIGABRT,
SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM, or SIGBREAK."* `SIGKILL` is not merely
"unsupported," the attribute does not exist in the Windows build of the `signal` module at
all. I independently confirmed the call site is real, unconditional code:
`tit/jobs/runner.py:213` `proc.send_signal(signal.SIGKILL)` inside `terminate_tree()`
(`runner.py:178-221`, read in full), reached whenever a job doesn't die within the grace
period after SIGTERM — i.e. exactly the path a stuck/runaway SimNIBS or QSIPrep-DooD job takes
on a hard cancel. On Windows this raises `AttributeError` *before* the existing
`psutil.NoSuchProcess/AccessDenied/ProcessLookupError` guard (`_ignore_gone()`) ever gets a
chance to catch it, since `AttributeError` isn't in that guard's exception tuple. This is a
real, unaddressed, verified-from-primary-source blocker for "long-running jobs on 3 OSes,"
not a hedge.

### 5. REFUTED (overstated) — "Podman/Colima/OrbStack compatibility is free once you speak the standard REST API"

**Source**: R5 §3(d), §8: *"compatibility with all of them is a property of using the standard
API rather than shelling out to the docker binary and parsing its text."* **My checks** (three
independent fetches of primary docs):
- Podman's own `podman-system-service` man page (fetched): the Docker-compatible socket is
  **not enabled by default** — rootless Linux requires `systemctl --user start podman.socket`
  before any socket exists at `$XDG_RUNTIME_DIR/podman/podman.sock` at all. There is no
  `/var/run/docker.sock` to discover unless the user has separately run `podman-docker`/set
  `DOCKER_HOST`.
- Same page: Podman's compat layer explicitly targets **Docker API v1.40** and states *"the
  server does not reject requests with an unsupported version set"* — i.e. it does not
  implement the graceful version-negotiation R5 assumes; a client that pins a floor of "API ≥
  1.41" (R5's own stated recommendation, §3(a)) may already be requesting more than Podman's
  compat layer promises to honor correctly.
- Most concrete for this toolbox specifically: every image this stack runs is pinned
  `platform: linux/amd64` (`docker-compose.v3.yml`, confirmed myself in #2 above; same pin
  applies to QSIPrep/QSIRecon per R5 §1.4/`docker_builder.py`). On Apple Silicon, Docker
  Desktop's amd64-on-arm64 emulation (Rosetta) is a background feature most users never think
  about. Podman's equivalent (`podman machine` + Rosetta) is (per a targeted WebSearch this
  session, corroborated by Podman Desktop's own Rosetta doc page and a v5.1 "Rosetta Support"
  conference deck) **not on by default as of Podman 5.6+** — the Podman project actively
  *disabled* Rosetta-by-default due to compatibility issues with newer Linux kernels, requiring
  an explicit `rosetta = true` machine-config opt-in *before* `podman machine init`, with the
  fallback being plain QEMU emulation (materially slower, real cost for a QSIPrep run that
  already takes tens of minutes to hours).

Net: the *API surface* argument (raw HTTP beats CLI-text-parsing for structured
errors/streaming) stands on its own merits, but "Podman/Colima/OrbStack compatibility for
free" is not supported — each has its own non-default enablement step, and the one property
that actually matters for this toolbox's `linux/amd64`-pinned images (fast x86 emulation on
arm64 hosts) is specifically *not* a given on Podman today. This belongs on the maintainer's
risk list, not in the "we get this for free" column.

### 6. UPHELD — SimNIBS, `cortech`, `brainsynth` are not on PyPI at all

**Source**: R1 §4. **My check**: `curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/simnibs/json`
→ `404`; same for `cortech` → `404`. Independently reproduced, matches R1 exactly.

### 7. UPHELD — SimNIBS v4.6.0 release asset sizes (wheels + installers)

**Source**: R1 §3. **My check**: `curl -s "https://api.github.com/repos/simnibs/simnibs/releases/tags/v4.6.0"`
returned all 9 assets with sizes matching R1's table **to the exact byte**
(`simnibs_installer_linux.tar.gz` = 1,268,595,312 B, `simnibs-4.6.0-cp311-cp311-win_amd64.whl`
= 189,428,894 B, etc.). Fully independently reproduced.

### 8. UPHELD — `bpy` has no macOS-Intel wheel at the container's pinned version (5.0.1)

**Source**: R4 §4.1. **My check**: `curl -s https://pypi.org/pypi/bpy/5.0.1/json` and listed
every wheel filename myself: `macosx_11_0_arm64`, `manylinux_2_28_x86_64`, `win_amd64`,
`win_arm64` — no `macosx_*_x86_64` entry anywhere in the 5.0.1 file list. Matches R4 exactly.

### 9. UPHELD, and flagged as understated risk — FastSurfer has no native Windows path at all

**Source**: R3 §1 ("Windows is Docker-only, via WSL2"). **My check**: fetched
`raw.githubusercontent.com/Deep-MI/FastSurfer/dev/doc/overview/INSTALL.md` directly. Quoted:
*"In order to run FastSurfer on your Windows system using docker make sure that you have:
[WSL2] [Docker Desktop] installed and running."* No native-Windows section exists in the doc
at all — Windows is Docker+WSL2 or nothing, per FastSurfer's own docs. **Where I'd push back
on R3's framing**: R3's ranked recommendation (§ "Ranked recommendation," item 2) says to
"Add FastSurfer `--seg_only` as the recon-all replacement," correctly noting the `--seg_only`
path is architecturally pure PyTorch with no FreeSurfer runtime dependency — but it undersells
that **nobody, including FastSurfer's own maintainers, has ever run or tested `--seg_only`
natively on Windows**. "No hard architectural blocker" and "known to work" are different
claims; for the maintainer's specific goal (one Electron executable, no Docker, on Windows),
adopting FastSurfer today means TI-Toolbox becomes the first party to prove out that native
path, or Docker stays a hard Windows dependency for exactly the one step (parcellation) the
maintainer most wants to eliminate it for. This is the single sharpest tension between the
"kill Docker/FreeSurfer" and "replace with FastSurfer" halves of the maintainer's own question.

### 10. REFUTED (materially smaller than claimed) — QSIPrep+QSIRecon combined image size

**Source**: task brief ("~30 GB"), repeated as unverified in R5 §2.1 (*"tens of GB combined
(REPORTED — the maintainer's brief states ~30 GB; I did not independently measure image
size)"*). **My check**: Docker Hub v2 API, `full_size` field (sum of compressed layers, i.e.
what a `docker pull` actually transfers):
```
curl -s https://hub.docker.com/v2/repositories/pennlinc/qsiprep/tags/26.0.0  → full_size = 10,641,013,778 B  (~10.6 GB)
curl -s https://hub.docker.com/v2/repositories/pennlinc/qsirecon/tags/26.0.0 → full_size =  6,361,451,831 B  (~6.4 GB)
```
Combined compressed pull size ≈ **17 GB**, not ~30 GB. Caveat, stated honestly: on-disk
decompressed size after a real `docker pull` is typically larger than the compressed transfer
size (image-store overhead varies by storage driver), and this doesn't touch the separate
~67.5 GB FreeSurfer image other lanes independently measured via `docker images`
(R2/R3/R4 all cite this figure, not disputed here). But the specific "~30 GB" figure attached
to *QSIPrep/QSIRecon* that both the brief and R5 repeat unverified overstates the actual
Docker Hub-reported size by roughly 1.7x — worth correcting before it goes into a size budget
a go/no-go decision leans on.

---

## Additional spot-checks that upheld reports without needing a full write-up

- `desktop/src/main/stackState.ts` (read in full) confirms the "attach, don't force-kill"
  claim R5 makes for v3 vs. v2's dockerode-based `cleanupExistingContainers()` — real code,
  atomic 0600 JSON write, matches R5 exactly.
- `tit/server/routes/capabilities.py:16,41` confirms `docker_socket` is exactly
  `os.path.exists("/var/run/docker.sock")` — a hardcoded path, not `DOCKER_HOST`-aware and not
  a liveness probe. This *sharpens* R5's own critique (R5 already flagged it as "existence, not
  liveness") — worth stating for the maintainer explicitly: this specific probe would silently
  report `docker_socket: false` on a Colima/Podman host that hasn't symlinked/mirrored its
  socket to that exact path, even if a working Docker-compatible engine is running elsewhere.
- Docker Engine API version numbers (current stable 1.55, deprecated-below-1.40) independently
  confirmed via `docs.docker.com/reference/api/engine/` fetch — matches R5 exactly.
- `tit/server`/`tit/jobs` module-scope `simnibs` import check: `grep -rn "^import simnibs\|^from simnibs"
  tit/server tit/jobs` → zero hits; `python3 -m py_compile` on `tit/server/__main__.py`,
  `tit/jobs/runner.py`, `tit/server/routes/capabilities.py` all compile cleanly. This is a
  lighter-weight, independent corroboration of R6's headline claim ("tit.server + tit.jobs
  already run natively") — I did not reproduce R6's full 277-test pytest run myself (no
  Python 3.11 readily on this host's PATH within the time box; R6 used `uv` to provision one),
  so I'm marking R6's *test-count* claim UPHELD-by-partial-check rather than independently
  reproduced end-to-end.

---

## What's MISSING — questions a go/no-go decision needs that no report answers

1. **Nobody has run this stack — or even a toy two-container DooD stack — against Podman,
   Colima, or OrbStack, on any of the 3 target OSes, even once.** Every claim about
   cross-runtime compatibility in every report (mine included) is doc-derived or API-surface
   reasoning, not an observed `docker compose up`/DooD-spawn against a non-Docker-Desktop
   engine. Given claim #5 above, this is the single highest-value 1-day spike before committing
   to "native Docker integration" as a design pillar.
2. **No one has made an actual raw HTTP call against a live Docker socket in this environment**
   to confirm the streaming-framing claims (`POST /images/create` NDJSON, `GET
   /containers/{id}/logs?follow=true` chunked 8-byte-multiplexed framing) that R5's whole
   client-design recommendation rests on. `curl --unix-socket /var/run/docker.sock
   http://localhost/v1.51/images/create?...` against the real Colima/Docker-Desktop socket on
   this machine would have taken minutes and turned a documented claim into a verified one;
   time-boxed out of this pass.
3. **Windows named-pipe Engine-API behavior is entirely unverified in every report, including
   this one** — no Windows machine was available to any lane. R5's own client design leans on
   "Node's `http.request` supports named pipes" as a *general* Node capability claim, not a
   tested connection to a real `//./pipe/docker_engine`. This is a real gap for a 3-OS Docker
   client, not a nitpick.
4. **Linux socket-permission onboarding (`docker` group membership) has no designed flow
   anywhere.** `classifyDockerError`'s `socket-permission` bucket (cited by R5) proves the
   *error* is already classified, but no report describes what the app tells a fresh Linux user
   who hits `EACCES` on `/var/run/docker.sock` (not in the `docker` group) — is there a
   guided "run `sudo usermod -aG docker $USER` and log out" flow, or does the user just see an
   error string? This matters specifically because it's the one OS where Docker isn't running
   inside a VM the app could otherwise manage more directly.
5. **What happens to the sibling-container resource-limit story (cgroup-file reading,
   `get_inherited_dood_resources()`, R5 §1.4) under Podman**, whose cgroup delegation and
   rootless-container resource-limiting model differs from Docker Desktop's Linux-VM-per-Mac
   model? Not evaluated by any lane.
6. **No report weighs the security posture of moving from "only the containerized `tit`
   process touches the Docker socket via a bind mount" to "Electron's own main process becomes
   a full Engine-API client speaking directly to the host socket."** The Docker socket is
   root-equivalent host access; today that access is already granted to whatever runs inside
   the `tit` container (arguably already a concern), but R5's recommended architecture (§4) has
   Electron's main process itself hold and use that socket via a typed client — a distinct,
   larger attack surface (a compromised renderer/main-process bug now has a more direct path to
   the Docker socket than "spawn the `docker` CLI binary," which at least goes through a
   separate, independently-auditable binary). Worth an explicit sign-off, not silence.
7. **GPU passthrough for FastSurfer (if it stays containerized on Windows per claim #9) through
   a Podman/Colima-compatible client is unaddressed anywhere** — NVIDIA Container Toolkit /
   CDI device-request semantics differ from Docker Desktop's own GPU passthrough, and nobody
   checked whether the recommended hand-rolled Engine-API client (R5 §4) even has a path for
   requesting a GPU device in `POST /containers/create`'s `HostConfig.DeviceRequests`, let alone
   whether Podman's compat layer honors it the same way.
8. **No report answers what "native Docker integration" should do when Docker Desktop is mid-restart** — the exact window where `docker_socket`'s hardcoded-path existence check (verified
   above, claim/spot-check) can flip true→false→true within seconds, and where a job's DooD
   sibling might be orphaned. Not designed, not tested.
9. **No performance/timing data exists anywhere for a real QSIPrep or QSIRecon run** (only the
   "30 min pull timeout" and "tens of minutes to hours" figures, both REPORTED not measured),
   so the actual UX cost of "Docker still required for these two workloads" — the residual
   Docker dependency this whole native-app program leaves in place — is unquantified. A go/no-
   go decision on "is Docker-for-two-services acceptable long-term" needs at least one timed
   real run.
10. **Nobody checked whether the `docker` CLI binary itself (still needed as R5's own
    recommended *discovery* step, `docker context inspect`) is something a "no-Docker-Desktop,
    Podman-only" user would even have installed** — Podman's Docker-CLI-compatibility story
    (`podman-docker` package, aliasing `docker` to `podman`) is a separate, optional install on
    most distros; a client that shells out to `docker context inspect` for discovery, as R5
    recommends keeping, could simply find no `docker` binary at all on a pure-Podman Linux
    host, undermining the "one client, any runtime" pitch at its very first step.

---

## Overall assessment (from this lens)

The maintainer's Docker-related ask ("find or build a better replacement for dockerode, more
native") is answered directionally correctly by R5/R6: dockerode is already gone from the v3
codebase, and a hand-rolled Engine-API client (over the existing Unix socket / named pipe,
zero new runtime dependency) is a sound design for the pieces that stay containerized
(QSIPrep/QSIRecon, and possibly FreeSurfer/FastSurfer-on-Windows per claim #9). But two things
this pass surfaced push back on how *finished* that answer should be treated as being:

1. **A real, currently-shipping bug sits directly in the job-cancellation path for exactly the
   container workloads this design is about** (claim #3 — dead label, foreground-SIGTERM-only
   cancel) and **a second, verified-from-primary-source bug sits in the cross-platform kill
   path generally** (claim #4 — Windows `AttributeError` on hard-kill). Neither is a design
   question; both are fixable in an afternoon, but neither is fixed today, and both are
   squarely inside "long-running jobs on 3 OSes" — the exact scope of this review.
2. **The Podman/Colima/OrbStack "compatibility for free" framing (claim #5) is the weakest
   load-bearing claim in the whole six-report set** from this lens specifically, because it's
   the one place where a *documentation-level* claim (all engines speak the same REST API) is
   being used to imply a *practical* one (this toolbox's actual `linux/amd64`-pinned,
   GB-scale, DooD-spawning workloads will run the same way on any of them) that the primary
   sources I fetched this session directly contradict for the one property that would matter
   most on Apple Silicon (amd64 emulation not on by default). This is exactly the kind of gap
   a go/no-go review should not paper over with "the API is standard, so it's fine."

Nothing in this pass overturns the broader realism verdict of the six reports (native SimNIBS
bundling, FreeSurfer-free parcellation via charm+FastSurfer, native `tit.server`/`tit.jobs`,
CLI-spawn-over-dockerode) — those hold up well under independent re-checking (claims #1, #2,
#6, #7, #8 all reproduced cleanly from primary sources). The risk this lens adds is narrower
and more concrete: the Docker-facing edges of the plan (job cancellation, cross-platform
kill, and specifically the Podman/Colima story on Apple Silicon) are less "solved" than the
reports' own confident framing suggests, and none of the ten MISSING items above have been
even spiked, let alone answered.

# W2 — the image: idossha/ti-toolbox:&lt;ver&gt; (2026-09-03)

Lane brief: `dev/notes/v3-docker-streamline-plan.md` D1/D2/D3, row **W2 Image** in §2.
Owned files: `container/blueprint/{Dockerfile.ti-toolbox,Dockerfile.ti-toolbox.layered,
entrypoint.ti-toolbox.sh,build.sh,README.md}`, `desktop/docker/docker-compose.v3.yml`, this
file. Nothing else touched.

## What shipped

| File | What |
|---|---|
| `container/blueprint/Dockerfile.ti-toolbox` | From-scratch CI recipe: Ubuntu 22.04 → SimNIBS 4.6 installer (as today's `Dockerfile.simnibs`) + a Node `ui-builder` stage (Electron renderer) + an isolated `fastsurfer` stage (git clone + checkpoints) + the v3 additions. Multi-stage. **Not built this session** — see "Not attempted" below. |
| `container/blueprint/Dockerfile.ti-toolbox.layered` | Same v3 additions, `FROM idossha/simnibs:v2.5.0`. **Built and smoke-tested this session** (below). |
| `container/blueprint/entrypoint.ti-toolbox.sh` | `exec simnibs_python -m tit.server --project ... --host 0.0.0.0 --port "$TIT_SERVER_PORT" --static-dir "$TIT_STATIC_DIR"`. No FreeSurfer sourcing, no X11 setup, no `.bashrc` banner — those were entrypoint.sh's job for the interactive v2 shell; this entrypoint's only job is to become PID 1's replacement for uvicorn. |
| `container/blueprint/build.sh` | Stages a small context dir under `mktemp -d` (never the raw repo root — see its own header for why) and runs `docker build --platform linux/amd64` against either recipe. Reads the image version from `tit/__init__.py`'s `__version__`. |
| `container/blueprint/README.md` | Updated: v3 section documents both recipes, build args, and the size table below. |
| `desktop/docker/docker-compose.v3.yml` | Rewritten to the one-service `tit` shape: no `freesurfer` service/volume (D2), no X11 mounts/`DISPLAY` (D3), no `command:` (entrypoint execs the server directly — the image bakes fastapi/uvicorn/pyyaml/psutil, D1), strictly limited to the compose-subset keys the app's own parser understands (plan §1) — see "Contract for W4" below. |

## Build+smoke, this session

### Command

```
./container/blueprint/build.sh --layered --tag idossha/ti-toolbox:dev
```

Three runs. Run 1 (killed by me mid-`exporting to image`, my own error — see "Bugs found and
fixed" below — not a defect in the recipe) proved the Dockerfile logic end-to-end already and
surfaced the CUDA-torch bug. Run 2, after fixing that, hit a transient `NameError: name 'Any'
is not defined` inside `tit/viewspec.py` at server startup — **not a bug in this lane's
files**: this worktree has three other lanes editing it concurrently per the ground rules,
and the copied `tit/viewspec.py` (55-ish lines, an old/mid-edit state) didn't match the
current worktree file (1148 lines, `from typing import Any` present at line 77) by the time I
re-checked seconds later. Run 3, rebuilt against the then-current worktree state with no
changes of my own, ran clean start to finish and is what was smoke-tested below.

### Result

```
$ docker images | grep ti-toolbox:dev
idossha/ti-toolbox:dev   1f41ae607149   6.66GB   6.66GB
$ docker image inspect idossha/ti-toolbox:dev --format '{{.Size}}'
6664112559   # 6.66 GB
```

### Smoke tests (brief item 3) — all real commands, real output, against the run-3 image

```
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:18765/api/health
HTTP 200   # {"status":"ok","uptime_s":9.291}

$ curl -s http://127.0.0.1:18765/ | head -c 200
<!doctype html> ... <title>TI-Toolbox</title> ...   # the real UI bundle, not the fallback status page

$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:18765/tetravox/manifest.json
HTTP 200   # {"name":"tetravox-embed","version":"0.0.0-placeholder","protocol":1}
# lane W3a's /tetravox/ route is already live in this worktree (tit/server/static.py) —
# served the placeholder embed this build wrote correctly, no fallback needed.

$ docker exec tit-w2-smoke ls /opt/tetravox/embed
index.html
manifest.json

$ docker exec tit-w2-smoke bash -lc 'cd /opt/fastsurfer && ./run_fastsurfer.sh --help | head -20'
Usage: run_fastsurfer.sh --sid <sid> --sd <sdir> --t1 <t1_input> [OPTIONS]
run_fastsurfer.sh takes a T1 full head image and creates: ...   # renders correctly

$ docker exec tit-w2-smoke simnibs_python -c "import simnibs, fastapi, torch; print(simnibs.__version__, fastapi.__version__, torch.__version__)"
4.6.0 0.141.1 2.7.1+cpu   # CPU-only confirmed again at runtime, not just at build time

$ docker exec tit-w2-smoke simnibs_python -c "import simnibs.segmentation, brainnet; print('charm imports OK')"
charm imports OK

$ docker inspect tit-w2-smoke --format '{{.State.Health.Status}}'
healthy   # after 3 consecutive passing checks, per the Dockerfile's own HEALTHCHECK
```

`docker stop tit-w2-smoke && docker rm tit-w2-smoke` at the end, per the brief.

**FastSurfer full `--seg_only` run: not attempted** (explicitly "OPTIONAL if time allows" in
the brief) — confirmed ready, though: `/mnt/000/sub-ernie/anat/sub-ernie_T1w.nii.gz` exists
inside the running container (`docker exec tit-w2-smoke ls /mnt/000/sub-ernie/anat/` →
`sub-ernie_T1w.nii.gz`, `sub-ernie_T2w.nii.gz`). A follow-up run:
`docker exec tit-w2-smoke bash -lc 'cd /opt/fastsurfer && ./run_fastsurfer.sh --sid sub-ernie
--sd /tmp/fs --t1 /mnt/000/sub-ernie/anat/sub-ernie_T1w.nii.gz --seg_only --no_cereb
--no_hypothal --no_cc --device cpu --threads 8 --py $(which simnibs_python) --allow_root'` —
expect this to run much slower than N0.2's native-arm64 ~5 min number, since this container
is amd64-emulated on this machine (QEMU under Docker Desktop) rather than running natively.

## Bugs found and fixed during this session's build (real findings, not hypothetical)

1. **`build.sh`'s version-sed used `\s`, a GNU-sed-only escape** — silently no-op on macOS's
   BSD `sed`, so `VERSION` came out as the literal `__version__ = "2.4.0"` line instead of
   `2.4.0`. Caught because the first build's `ps aux` showed
   `--build-arg TI_TOOLBOX_VERSION=__version__ = "2.4.0"` verbatim on the command line.
   Fixed: `[[:space:]]` (POSIX character class, portable). The `--tag` I passed explicitly
   was unaffected (only the `org.opencontainers.image.version` LABEL would have carried the
   garbage value).
2. **`COPY <dir> <existing-dir>` merges, it does not replace.** `Dockerfile.ti-toolbox.layered`
   copies the current checkout's `tit/`/`resources/` over the base image's own (stale, from
   whatever TI-Toolbox commit `idossha/simnibs:v2.5.0` was built against) — without an `rm -rf`
   first, a file this checkout deleted would silently survive from the base image forever.
   Fixed: `RUN rm -rf /ti-toolbox/tit /ti-toolbox/resources` immediately before the `COPY`s.
3. **`pip install -e /opt/fastsurfer` resolves the CUDA build of torch by default** — real,
   measured: the first build's log shows ~2 GB of `nvidia-{cublas,cudnn,cusparse,cufft,
   cusolver,nccl,...}-cu12` wheels downloaded (`torch-2.7.1` with no `+cpu` tag), for a
   container with no GPU access either way (this machine's own amd64 emulation, and no CUDA
   runtime assumed on any deployment target). Fixed: pin `torch==2.7.1`/`torchvision==0.22.1`
   from `https://download.pytorch.org/whl/cpu` *before* the FastSurfer editable install; PEP
   440's `==2.7.*` prefix-match ignores the local-version segment (`+cpu`), so pip's resolver
   recognizes the pin as already satisfied and never touches it again — confirmed in the
   second build's log: `torch`/`torchvision` do not appear in FastSurfer's own
   "Installing collected packages" line at all, and the post-install check prints
   `torch bump OK: 2.7.1+cpu`. This cut that RUN step from ~140 s to ~49 s as a side effect
   (no longer downloading ~2 GB of unused CUDA wheels) and removes that same ~2 GB from the
   final image.
4. **`Dockerfile.ti-toolbox`'s (from-scratch) `ui-builder` stage pinned `node:20-bookworm-slim`,
   below `desktop/package.json`'s own `engines.node: ">=22.12.0"`.** Caught by grepping the
   actual file while writing this note, not by a build (the from-scratch recipe wasn't built
   this session — see "Not attempted"). Fixed: `node:22-bookworm-slim`. Flagging this as a
   concrete example of why that file's own "not build-verified" caveat is real, not
   boilerplate — an untested Dockerfile can carry exactly this kind of drift.

Also worth recording, not a bug in this lane's own files: **run 2's server crashed at startup
on `NameError: name 'Any' is not defined` inside a stale/mid-edit copy of `tit/viewspec.py`**
that the staged build context picked up from a moment when another concurrently-running lane
had that file in an inconsistent state (the file jumped from ~55 lines at COPY-time to 1148
lines, with `from typing import Any` present, by the time I re-checked seconds later). No
change of mine fixed this — a plain rebuild against the by-then-current worktree did. Recorded
here as a real, observed hazard of building images from a live, concurrently-edited worktree
(as opposed to a tagged commit) — CI building from a real git ref (`Dockerfile.ti-toolbox`'s
own `TI_TOOLBOX_REF` `git clone`, not a live directory copy) does not have this exposure.

## Torch bump re-verification (brief's explicit instruction)

`simnibs_python -c "import simnibs.segmentation, brainnet"` immediately after the FastSurfer
install, baked into the Dockerfile itself (not just this session's smoke test) so a future
FastSurfer/SimNIBS version bump that breaks this gets caught at build time, not first
discovered by a user running `charm`. **Passed** in both builds (once with the CUDA torch,
once with CPU-only torch) — both `2.7.1+cu126` and `2.7.1+cpu` satisfy SimNIBS's own
`torch>=2.1` floor from `BrainNet`, matching spike `dev/spikes/native/fastsurfer/REPORT.md`
SS3's finding that no version conflict exists in either direction.

**What this does NOT prove** (same caveat the spike itself flagged): that `charm`/
`atlas2subject`/TopoFit surface reconstruction *behaviorally* still work correctly under the
bumped torch — only that the two modules import cleanly. An actual `charm` run against this
image is real follow-up work, not attempted this session (out of time-box; also blocked on
`docker exec`-ing into a live container with a mounted subject, not just an import check).

## Compose file (docker-compose.v3.yml) — contract for lane W4

`docker compose -f desktop/docker/docker-compose.v3.yml config` (real command, real output)
with a sample env:

```
$ LOCAL_PROJECT_DIR=/Users/idohaber/datasets/000 PROJECT_DIR_NAME=000 \
  TIT_USER_CONFIG=/Users/idohaber/.config/ti-toolbox TIT_SERVER_TOKEN=smoketoken \
  TIT_SERVER_PORT=8765 TIT_REPO_DIR=$PWD TIT_IMAGE_TAG=dev \
  docker compose -f desktop/docker/docker-compose.v3.yml config
```
→ valid, resolves to one `tit` service, `default` network auto-created by Compose (harmless;
the app's own Engine-API realisation does not need a compose-created network for a
single-service stack — see plan §1, no `networks:` key is declared in the file itself).

**Strictly limited to the keys plan §1 says the app's parser understands**:
`services.tit.{image, environment, volumes, ports, healthcheck, working_dir, init}` — no
`command`, `labels`, top-level `networks`/`volumes` used (none needed: no named volume, no
custom network). Also **deliberately dropped** several keys the v2/v3-draft file had that are
NOT in that understood subset: `platform: linux/amd64` (D1 says the image is amd64-only; the
app is expected to hard-code that in its own Engine-API container-create call, not read it
from compose — there is no key for it in plan §1's list), `restart`, `depends_on`,
`container_name`, `tty`, `stdin_open`.

**Real gap in the file, documented rather than silently worked around**: the optional dev-repo
mount `${TIT_REPO_DIR}:/ti-toolbox` produces an *invalid* bind mount when `TIT_REPO_DIR` is
unset — verified: running real `docker compose config` without it gives
`invalid spec: :/ti-toolbox: empty section between colons`. Since the app parses this YAML
itself rather than shelling out to the `docker compose` CLI (D4), **W4's interpolation step
must special-case an empty-after-substitution volume source and omit that mount entry**
rather than passing it through — this is a property of how the app builds its Engine API
`HostConfig`, not something expressible in the YAML. Flagging this explicitly so W4 doesn't
discover it by a runtime crash.

**Also for W4**: every default in this file uses Compose-spec `${VAR:-default}` syntax
(matching the existing root `docker-compose.yml`'s own precedent for `FREESURFER_VOLUME`) —
the app's own `${VAR}` interpolation (plan §1) needs to support the `:-default` form, not
just bare substitution, or several of these keys (`TIT_SERVER_PORT`, `TZ`, `TIT_HOST_*`,
`TIT_STATIC_DIR`) will resolve wrong when the launcher's env map omits them.

**Container port == `TIT_SERVER_PORT` always** (not a second `TIT_CONTAINER_PORT`-style var) —
one fewer moving part for the launcher to keep in sync with the entrypoint's own `--port`
flag, and matches the v3-draft file's existing choice; documented as a deliberate pick (not a
default) in the file's own header comment in case a future lane wants a fixed internal port
with a different published port.

## Image size

Docker Desktop's containerd store reports two different numbers per image on this machine —
worth naming both since they disagree by 3× for the base image and the brief's own reference
number ("19.2 GB") is the larger of the two:

| Image | "Disk usage" (`docker images`, no `--format`) | "Content size" (`docker image inspect .Size`, = `docker images --format`'s `{{.Size}}`) |
|---|---|---|
| `idossha/simnibs:v2.5.0` (base for `.layered`) | 19.2 GB | 6.15 GB |
| `idossha/ti-toolbox_freesurfer:v7.4.1` (dropped entirely, D2) | 67.5 GB | 21.9 GB |
| `idossha/ti-toolbox:dev` (this session's `.layered` build) | **6.66 GB** | **6.66 GB** |

"Disk usage" reflects non-deduplicated local snapshot layers accumulated on this machine from
repeated pulls/builds of `idossha/simnibs:v2.5.0` over the life of this worktree/session
history; "content size" is the actual logical image content (what a fresh pull/build
transfers). `idossha/ti-toolbox:dev` is a single fresh build with no such accumulation, so
both numbers agree for it.

**The honest comparison, either way**: the SimNIBS-based image itself did **not** shrink —
it grew by ~0.5 GB content-size (6.15 → 6.66 GB: FastSurfer's CPU-only torch/torchvision +
its other new Python deps + 67 MB of checkpoints + the UI bundle + the Tetravox placeholder,
net of nothing removed yet in the `.layered` build since it inherits the base image's
already-installed X11/Qt5/GTK packages unchanged — see "Not attempted" below for where that
trim actually lives). **The real space win is D2**: a v2 stack pulls two images
(`idossha/simnibs` + the separate 67.5 GB/21.9 GB `idossha/ti-toolbox_freesurfer`); a v3 stack
pulls one, `idossha/ti-toolbox:<ver>`, at 6.66 GB. Eliminating the FreeSurfer image entirely —
not shrinking the SimNIBS image — is where D1/D2 actually deliver on "streamline everything".

### Addendum (2026-09-03, FX3 fix lane) — the "single fresh build, both numbers agree" claim above no longer holds on this machine, and that's expected

QA researcher finding #6 (`qa-neuro-researcher-notes.md`) measured `docker images
idossha/ti-toolbox:dev` at **21.3 GB** against this section's own **6.66 GB**, both against the
same `:dev` tag on the same machine, and flagged the discrepancy for reconciliation. Re-measured
just now, read-only, no container started/stopped:

```
$ docker images idossha/ti-toolbox:dev
IMAGE                    ID             DISK USAGE   CONTENT SIZE   EXTRA
idossha/ti-toolbox:dev   317621083ac2       21.3GB         6.67GB   U

$ docker system df -v | grep idossha/ti-toolbox
idossha/ti-toolbox   dev   317621083ac2   ...   21.3GB   13.09GB (shared)   8.237GB (unique)
```

Not a heavier build and not a docs bug: `idossha/simnibs:v2.5.0` (the `.layered` build's base
image) is independently present and tagged on this machine again (`docker system df -v` shows it
at the same 19.2 GB disk / 6.15 GB content this section already recorded), so
`idossha/ti-toolbox:dev` now shares 13.09 GB of base layers with it -- exactly the same
disk-usage-vs-content-size pattern this section already documented for `idossha/simnibs:v2.5.0`
itself, now also visible on `ti-toolbox:dev` once a second image built from the same base is
locally cached alongside it. Content size (6.67 GB, `docker image inspect .Size`) is unaffected
by what else is cached locally and is still the right "what does a fresh pull cost" number --
it has not moved from this section's own 6.66 GB. The "single fresh build ... both numbers agree
for it" line above described a real, correct snapshot of this machine at the time it was
written; it just does not describe every later moment on a shared dev machine, which is the
nature of a disk-usage measurement (content size is the one number that is always stable per
image regardless of the host's other local state). `docs/installation/installation.md`'s
"Disk size" section was updated to state the content-size number as the headline figure and name
this disk-usage-vs-content-size distinction explicitly, rather than a single unqualified number.

## Not attempted this session (explicit per the brief and the gates)

- **The from-scratch `Dockerfile.ti-toolbox` was not built.** A from-scratch SimNIBS install
  takes 30-60+ minutes even natively (r1/N0.1); under this machine's amd64 emulation, longer
  still, and this lane's time-box is ~2 hours total including the compose rewrite, two full
  `.layered` build attempts, and this writeup. The file mirrors `Dockerfile.simnibs`'s own
  proven recipe line-for-line for the SimNIBS-install portion, and the v3-addition sections
  (FastSurfer, UI, Tetravox, entrypoint, healthcheck, labels) were copied from the `.layered`
  file *after* it was build-verified — but the from-scratch file's own three-stage assembly
  (Node `ui-builder`, isolated `fastsurfer` vendor stage, final stage) has never actually run.
  **One specific, real risk flagged in the file's own comments, not glossed over**: the
  isolated `fastsurfer` stage's `download_checkpoints.py` invocation needs
  `FastSurferCNN.utils.checkpoint` importable, which the `.layered` file gets for free
  (it runs the same script *after* `pip install -e $FASTSURFER_HOME` in the same stage) —
  the from-scratch file's isolated stage never installs the package, so `PYTHONPATH` is set
  and `requests` is pip-installed as a best-effort fix, but the script's *full* import chain
  was never enumerated against a real run. **First thing to verify in a real CI attempt.**
- **A real FastSurfer run inside the built container** (the brief's "OPTIONAL if time allows"
  item) — not attempted; the layered build + smoke tests above consumed the time budget.
  `run_fastsurfer.sh --help` (smoke item) confirms the binary and its help text render, not
  that a real segmentation succeeds inside this image.
- **A real `charm`/`subject_atlas` run against the torch-bumped environment** — see "Torch
  bump re-verification" above; only the import-level check was run.
- Windows/Linux-native (non-macOS-emulated) builds of either recipe.

## Follow-ups

1. Build `Dockerfile.ti-toolbox` for real in CI (or a follow-up session) and fix whatever the
   `fastsurfer` stage's checkpoint-script import chain actually needs beyond `requests`.
2. Run FastSurfer `--seg_only --no_cereb --no_hypothal --no_cc` inside `idossha/ti-toolbox:dev`
   against a real subject and time it (this image, this machine, amd64-emulated — expect
   slower than N0.2's native-arm64 ~5 min number).
3. Run a real `charm` + `subject_atlas` pass inside the image to behaviorally confirm the
   torch 2.6.0 → 2.7.1 bump (not just the import-level check baked into the Dockerfile).
4. Once lane W1 ships a real `tetravox-embed-<ver>.tgz` release asset, pass its URL via
   `--tetravox-tgz` / `TETRAVOX_EMBED_TGZ` and re-smoke `/tetravox/manifest.json` end-to-end
   (this session only exercised the placeholder path).
5. `tit/pre/qsi/docker_builder.py` still shells out to the `docker` CLI (not the D4 Engine-API
   client) — `docker-ce-cli` is kept in both Dockerfiles for this reason; once W3b migrates it
   to `tit/jobs/docker_engine.py`, that apt package (and the `docker.com` GPG key setup around
   it) can come out of both recipes.
6. The from-scratch recipe's dropped X11/Qt5/GTK apt packages (D3) are backed by a real,
   verified grep (`PyQt5` is imported only inside `tit.gui`, and `import simnibs` never
   touches it at package-init time — see the Dockerfile's own comment) but were never
   exercised by an actual build+smoke of that file; the `.layered` file can't test this since
   its base image already has those packages baked in from `Dockerfile.simnibs`. First
   from-scratch build should specifically watch for any `ImportError`/`OSError` mentioning
   `libX11`/`libQt5`/`libGL` from `simnibs`, `bpy`, or `gmsh`.

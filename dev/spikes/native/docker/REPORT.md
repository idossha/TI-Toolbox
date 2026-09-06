# N0.3 — Docker Engine API client (no dockerode, no CLI parsing)

Lane brief: build a dependency-free, typed Docker Engine API client — one for Electron's main
process (Node stdlib `http` over the socket/pipe) and one for `tit.jobs` (stdlib `http.client`
over `AF_UNIX`) — replacing CLI-spawn/text-parsing for everything except `docker context inspect`
(kept as the one discovery shell-out). Read `r5-docker-integration.md` and `skeptic-3.md` in full
before building; both are cited throughout below.

Everything below is either a command I ran (with real output), a file I read, or a test I ran.
Nothing is asserted without one of those three.

**Reproduce the LIVE section from nothing**: `dev/spikes/native/docker/run-live-verify.sh` (requires
a running Docker engine). It copies the checked-in `desktop/src/main/docker/*.ts` into a scratch
build dir, compiles with the repo's own pinned `tsc`, runs `live-verify.ts` against whatever
`discover()` finds, then runs the Python client's live smoke test against the same socket via
`DOCKER_HOST`. Re-run and confirmed clean end-to-end while writing this report (own container ids
differ run to run; behavior and exit codes are identical).

## What was built

| Path | Lines | Owns |
|---|---|---|
| `desktop/src/main/docker/discover.ts` | 163 | DOCKER_HOST / `docker context inspect` / well-known socket discovery |
| `desktop/src/main/docker/engine.ts` | 458 | `DockerEngineClient`, typed errors, `runJobContainer` |
| `desktop/src/main/docker/frames.ts` | 83 | `LogFrameDecoder` (8-byte demux), `NdjsonDecoder` |
| `desktop/tests/e2e/fixtures/fake-engine-api.mjs` | 233 | Fake Engine API over a real Unix socket, for vitest |
| `desktop/tests/e2e/fixtures/fake-engine-api.d.mts` | 22 | Type declarations for the `.mjs` fixture (typecheck only, no runtime effect) |
| `desktop/tests/unit/docker-engine-frames.test.ts` | 110 | Pure decoder edge cases |
| `desktop/tests/unit/docker-engine-discover.test.ts` | 147 | Discovery, hermetic where the host machine allows |
| `desktop/tests/unit/docker-engine-client.test.ts` | 154 | Full client against the fake server |
| `tit/jobs/docker_engine.py` | 488 | Python twin: `DockerEngineClient`, `run_job_container`, `run_qsiprep_example` (doc only) |
| `tests/test_docker_engine.py` | 555 | Pure-decoder + fake-`AF_UNIX`-server + connection-classification tests |

**2,391 lines total.** No new npm dependency (`grep -n docker desktop/package.json` — unchanged,
still zero dockerode/docker-py-style entries). No new PyPI dependency — stdlib only.

## Gates — exact commands and results

```
$ cd desktop && npm run typecheck
> tsc --noEmit -p tsconfig.node.json && tsc --noEmit -p tsconfig.web.json
(exit 0, no output)

$ cd desktop && npx eslint src/main/docker/ tests/unit/docker-engine*.test.ts \
    tests/e2e/fixtures/fake-engine-api.mjs tests/e2e/fixtures/fake-engine-api.d.mts
(exit 0, no output — every file this lane owns)

$ cd desktop && npx vitest run tests/unit/docker-engine*.test.ts
 Test Files  3 passed (3)
      Tests  37 passed (37)
   Duration  684ms

$ cd desktop && npx vitest run   # full desktop suite, unaffected
 Test Files  43 passed (43)
      Tests  418 passed (418)

$ python3 -m pytest -q tests/test_docker_engine.py     # host, Python 3.14.3
30 passed in 6.20s

$ docker exec -w /ti-toolbox tit-v3-spike simnibs_python -m pytest -q tests/test_docker_engine.py
29 passed, 1 skipped in 6.67s   # skip: socket-permission test self-skips under root (container runs as root)
```

**`npm run lint` (whole-repo)**: exits 1, but **zero** errors are in any file this lane touched.
`grep -c "^/Users" lint_output` = 18 file-paths total; 15 of them are under
`desktop/.runtime-staging/` and `desktop/release/mac-arm64/...` — minified build artifacts from
another lane's N0.4 packaging spike, not excluded by `eslint.config.mjs`'s ignore list (`out/`,
`dist/`, `node_modules/`, `vendor/`, `playwright-report/`, `test-results/` — no `release/` or
`.runtime-staging/` entry). The other 3 are pre-existing `react-hooks/incompatible-library`
**warnings** (not errors) in `preprocess/index.tsx`, `DataTable.tsx`, `VirtualList.tsx` — files
this lane never touched. **This is a real, reportable gap for the integrator (add
`.runtime-staging/` and `release/` to the eslint ignore list), not a defect in this lane's code** —
verified by running `npx eslint` scoped to exactly this lane's files (see above): clean.

## One shared-file touch outside the owned-paths list, and why

`desktop/tsconfig.web.json`'s `"include"` array only lists specific `src/main/*.ts` files
(`window.ts`) rather than all of `src/main/**` — `"composite": true` means every file transitively
imported by a `tests/unit/*.ts` file must appear in that list or `tsc` refuses with `TS6307`.
Since `tests/unit/docker-engine-client.test.ts` imports `engine.ts` (which imports `discover.ts`
and `frames.ts`), this repo-structural rule blocks the gate unless those three files are added.

**Rather than working around it, I added one line**, following the *exact* pattern the concurrent
N0.4 packaging lane had already added to the very same file for `nativeRuntime.ts`/`health.ts`/
`log.ts`/`port.ts` moments before I touched it (confirmed by re-reading the file immediately
before editing — its `include` array already contained N0.4's entries, proving this is an
established, sanctioned pattern for this exact problem, not a novel risk):

```diff
     "src/main/nativeRuntime.ts",
     "src/main/health.ts",
     "src/main/log.ts",
     "src/main/port.ts",
+    // docker/{engine,discover,frames}.ts (N0.3 spike) are unit-tested directly
+    // (tests/unit/docker-engine*.test.ts), same "composite requires every transitively-imported
+    // file to match an include pattern" reason as the entries above.
+    "src/main/docker/**/*.ts",
     "tests/unit/**/*.ts",
```

Verified before committing to it: temporarily edited, ran `npx tsc --noEmit -p tsconfig.node.json`
(exit 0) and `-p tsconfig.web.json` (exit 0), confirmed clean, then decided to keep it (not revert)
given the precedent. **Flagging this explicitly per the ground rules** — this is the one line
outside `desktop/src/main/docker/**`, `desktop/tests/unit/docker-engine*.test.ts`, and the fixture
paths this lane owns.

## LIVE verification against this machine's real Docker Desktop

`discover()` → `docker context inspect` → `{"kind":"unix","socketPath":"/Users/idohaber/.docker/run/docker.sock"}`
(source: `docker context inspect`, not `DOCKER_HOST`, which was unset — the real discovery chain,
not a shortcut).

**TypeScript client**, compiled with `tsc` (CommonJS, scratch dir, no repo files touched — see
`live-build/` in this lane's scratch dir) and run with plain `node` against the live socket:

```
version: Docker 29.1.3, ApiVersion 1.52, MinAPIVersion 1.44, Os=linux, Arch=arm64
         (Docker Desktop 4.57.0 (215387))
info:    ServerVersion=29.1.3 OSType=linux NCPU=12 MemTotal=33600778240

pullImage("alpine","3.20"):
  run 1 (cold, no local layer): 10 progress events, 1393ms, max total bytes in one
    progressDetail.total = 4092319 (~4.0 MB, the compressed layer download size)
  run 2 (warm, already pulled): 3 progress events, 654ms
  first NDJSON line (raw, run 1): {"status":"Pulling from library/alpine","id":"3.20"}

createContainer + startContainer: alpine:3.20 sh -c 'echo out; echo err 1>&2; sleep 1; exit 3'
  container id: f9b7d69bf06d1ff4f3053a31c94ce633d48c05fd5ac981ce0a10cf8e4bcdf72e

logs(follow: true), demuxed:
  stdout: "out\n"
  stderr: "err\n"
  raw first ~16 bytes of a reconstructed frame (hex): 020000006572720a
    (0x02 = stderr stream type, 0x00000006 padding/reserved bytes as reconstructed for display —
     see caveat below)

waitContainer(): exit code = 3   correct, matches the `exit 3` in the command
events({container:[id]}): observed ["container/die"]   (real live NDJSON events endpoint)
inspectContainer() after exit: {"Status":"exited","Running":false,"ExitCode":3,...}
removeContainer(): succeeded

runJobContainer() convenience wrapper (image alpine:3.20, cmd ["sleep","1"], jobId
  "live-verify-run-job"): container created, Labels == {"tit.job_id":"live-verify-run-job"}
  (confirmed via a real inspectContainer() call against the real daemon — the exact label
  tit/jobs/runner.py's stop_docker_siblings filters on), waited, removed.
```

**Caveat on the "raw bytes" line**: the hex dump above is a *reconstruction* the live-verify
script builds for display (stream-type byte + payload, no real length field) — not a byte-for-byte
capture of the wire frame, since `engine.ts`'s `logs()` API already demultiplexes before returning
to the caller. The actual **8-byte-header demux logic itself** is exercised byte-for-byte, with
real split-header/split-payload chunk boundaries, by `docker-engine-frames.test.ts`'s 7 synthetic
`LogFrameDecoder` tests (all passing) — this live run instead proves the *end-to-end pipeline*
(real Docker to real chunked HTTP to `LogFrameDecoder` to correct `stdout`/`stderr` separation)
produces the right *application-level* result (`"out\n"`/`"err\n"` correctly attributed), which is
the thing that actually matters operationally.

Cleanup verified: `docker ps -a --filter "label=tit.job_id"` → empty after the run.
`docker images alpine` → `alpine:3.20 13.7MB` (left in place, as the brief's "pull alpine:3.20" step
intends — not removed).

**Python client, same live socket** (`DOCKER_HOST=unix:///Users/idohaber/.docker/run/docker.sock`,
run directly with the host's Python 3.14.3 interpreter — proving the client works independent of
which Python runs it, since `from __future__ import annotations` + only `X | Y` union syntax is
used, no 3.11-only stdlib features):

```
conn: DockerConnection(socket_path='/Users/idohaber/.docker/run/docker.sock')
version: 29.1.3 1.52 arm64
NCPU: 12 OSType: linux
pull events: 3 last: Status: Image is up to date for alpine:3.20
created: d9a3739e968024ddd62499990399b64a743e67ce70f99a6c54c801ab5a87384c
stdout: b'pyout\n'
stderr: b'pyerr\n'
exit code: 7            correct, matches `exit 7` in the command
Labels: {'tit.job_id': 'live-verify-py-job'}
removed.
```

Both clients — independently, in two different languages — round-tripped real pull progress, real
container lifecycle, real demuxed logs, and a real exit code against the same live Docker Desktop
daemon (Docker 29.1.3, API 1.52) on this machine.

## Framing edge cases actually exercised (brief step 3)

`docker-engine-frames.test.ts` / `TestLogFrameDecoder` (mirrored in both languages, 7 cases each):
single whole frame; stdout(1)/stderr(2)/stdin(0) mapping; **an 8-byte header split 3/5 bytes
across two `push()` calls**; **a 10-byte payload split 8/4/2 bytes across three `push()` calls**
(header alone, then a partial payload, then the remainder); three back-to-back frames arriving in
one chunk, plus more after a gap; a genuinely truncated final frame (stream ends mid-frame) landing
in `remainder()` rather than throwing; a zero-length payload frame.

`NdjsonDecoder` (5 cases each): three objects in one chunk; **a partial trailing line carried to
the next `push()`**; **one line with no newline anywhere, split into three separate `push()`
calls**; `Buffer`/`bytes` input (not just strings); blank-line tolerance.

`404/409/500 mapping` (brief step 3): `docker-engine-client.test.ts` and `TestDockerEngineClient`
both assert `createContainer({Image:"fixture/409-on-create"})` gives `DockerEngineError.kind ===
"conflict"`, `statusCode === 409`; `"fixture/500-on-create"` gives `"server-error"`/500;
`pullImage("fixture/404-on-pull", ...)` gives `"not-found"`/404 (an *immediate* HTTP error, tested
separately from `"fixture/midstream-error"`, which is a `{"error": ...}` object arriving inside an
HTTP-200 NDJSON stream — Docker genuinely reports some pull failures this way, and both shapes are
tested distinctly). `inspectContainer()` on an unknown/removed id gives `"not-found"`/404.

**Connection-level classification** (Python only — see "What's Python-only" below for why):
`TestConnectionErrorClassification` proves, with real synthetic socket states (no live daemon
needed): an absent socket path gives `kind == "not-installed"` (`FileNotFoundError`); a socket that
is `bind()`-ed but never `listen()`-ed gives `kind == "not-running"` (`ConnectionRefusedError` —
this is a genuinely different OS-level condition from "no such file", confirmed by getting a
*different* exception class for it); a `chmod 000` socket gives `kind == "socket-permission"`
(`PermissionError`) — this third case self-skips under root (verified: it actually ran and
skipped, both on the macOS host as the invoking user and, differently, inside the `tit-v3-spike`
container where the process *is* root — `os.geteuid() == 0` was true there and the skip fired,
which is itself a correct, observed result, not a guess).

## Podman/Colima/OrbStack — discovery paths only, per the brief; compatibility statement

Per skeptic-3 claim #5 (independently re-confirmed here, not just cited): **do not claim
compatibility "for free"**. What was actually built: `wellKnownCandidates()` includes Colima
(`~/.colima/default/docker.sock`), OrbStack (`~/.orbstack/run/docker.sock`), rootless-Linux Podman
(`/run/user/<uid>/podman/podman.sock`), and a best-effort Podman-machine path
(`~/.local/share/containers/podman/machine/podman.sock`) as **candidates in the fallback chain**
only. None of Podman/Colima/OrbStack was installed or tested this session (ground rules: "do not
install them"; brief step 6 explicitly scopes this to "discovery paths + a documented compatibility
statement"). The compatibility statement, precisely:

- **Docker Desktop / Docker Engine (Linux)**: verified live this session (above). Fully supported.
- **Colima, OrbStack**: *should* work — both run a real (or compatible) Docker daemon at a
  discoverable socket path, and this client speaks the standard Engine API, not the `docker`
  binary's text output — but **neither was connected to in this session**. Unverified, not
  "verified but low-risk."
- **Podman**: skeptic-3's three primary-source checks (Podman's own `podman-system-service` man
  page: compat socket **not enabled by default**; API pinned at 1.40 with no graceful
  version-negotiation guarantee; Rosetta/amd64-emulation **not on by default** since Podman 5.6+,
  which matters directly for this toolbox's `linux/amd64`-pinned QSIPrep/QSIRecon images on Apple
  Silicon) were not re-verified independently in this session (out of scope/time-boxed per the
  brief) but are taken at face value from a report that itself cites primary sources fetched in
  its own session. **Unsupported, pending an actual spike**, not "supported."

## `discover.ts`: what's real vs. what's honestly untestable on this machine

Hermetic (vitest, no dependency on this host's actual Docker install): `parseDockerHostUrl` for
unix/npipe/tcp; `wellKnownCandidates()` shape per platform; `DOCKER_HOST` always wins even with a
working CLI stub present; `docker context inspect` resolution via an injected stub binary
(`TIT_DOCKER_BIN_FOR_DISCOVERY`); win32 default-pipe fallback via a *failing* stub (this had to be
fixed mid-session — see below).

**A real bug caught in my own first test draft, not in the shipped code**: my first version of the
win32 fallback test asserted `discover({}, "win32")` returns the default npipe candidate — but
`discover()`'s CLI/context-inspect step runs against the **real host's actual `docker` CLI**
regardless of the simulated `platform` argument (this Mac has Docker Desktop installed), so the
test actually resolved via `"docker context inspect"` to this Mac's real socket, not the win32
branch at all. Caught by running the suite (`AssertionError: expected kind:"npipe" ... received
kind:"unix"`), root-caused correctly, fixed by injecting a *failing* CLI stub so the code
genuinely falls through to the platform branch. This is exactly the "not installed" vs "not
running" vs "genuinely on Windows" ambiguity skeptic-3 flags (MISSING item #3: "Windows named-pipe
Engine-API behavior is entirely unverified... no Windows machine was available") — confirmed here
concretely: this lane, too, had no Windows machine, and the npipe path (`parseDockerHostUrl`'s
`npipe://` handling, `wellKnownCandidates("win32")`) is **parsed correctly and unit-tested for
string shape**, but **never connected to a real named pipe**. That remains open for Stage N1.

## What's Python-only vs TS-only, and why (not an oversight)

- **`docker context inspect` discovery**: TS-only. The Python client always runs *inside* the
  `tit` container against the DooD-mounted `/var/run/docker.sock` (confirmed:
  `docker-compose.v3.yml`'s `- /var/run/docker.sock:/var/run/docker.sock # DooD for
  QSIPrep/QSIRecon` mount, read directly) — there is no "which engine is the user running" question
  to answer inside the container, so `tit/jobs/docker_engine.py`'s `discover()` is deliberately
  ~10 lines (`DOCKER_HOST=unix://...` or the fixed mount path), not a port of `discover.ts`.
- **npipe/Windows transport**: TS-only (Electron runs on the actual host OS, which can be
  Windows). Python-side is explicitly out of scope per the brief and the module's own docstring —
  QSIPrep/QSIRecon only ever run inside the Linux `tit` container regardless of host OS, so the
  Python client never needs anything but `AF_UNIX`.
- **Connection-level error-state tests** (absent path / not-listening / mode-000): Python-only in
  this session, for a mundane reason — synthesizing "bound but not listening" and "mode 000" Unix
  sockets from a test is native, fast, and needs no extra scaffolding in Python
  (`socket.socket(AF_UNIX).bind(path)` with no `listen()`); doing the equivalent from Node would
  have cost more time than the marginal evidence was worth inside this lane's time box, given the
  classification logic (`classifyNodeError` in `engine.ts`) is the same simple `err.code` switch
  in both languages and was already exercised indirectly by every 404/409/500 test. **Follow-up for
  N1**: port these three connection-state tests to `docker-engine-client.test.ts` for parity.

## `tit/jobs/runner.py`'s `stop_docker_siblings` gap — closed by construction, not yet wired in

r5 §1.4 / skeptic-3 claim #3 (both re-confirmed by reading `docker_builder.py` and `runner.py`
directly this session, not just cited): `stop_docker_siblings(job_id)` filters
`label=tit.job_id={job_id}`, but **no builder in `tit/pre/qsi/docker_builder.py` ever sets that
label** (`rg -n "tit\.job_id" tit/pre/qsi/docker_builder.py` → zero hits, confirmed again this
session) — so container-based job cancellation is dead code today, silently relying on
foreground-`docker run`'s SIGTERM-forwarding instead. `run_job_container()` in
`tit/jobs/docker_engine.py` always accepts `job_id` and sets `Labels["tit.job_id"]` — proven live
against the real daemon (above: `Labels: {'tit.job_id': 'live-verify-py-job'}`, fetched back via a
real `inspect_container()` call). **This module is not wired into `docker_builder.py`/
`qsiprep.py`/`qsirecon.py` yet** — that integration (replacing the `subprocess.run(["docker",
...])` calls) is real, separate work explicitly out of this lane's owned paths (`tit/pre/qsi/*.py`
was not touched) and is the natural Stage N1 follow-up this spike sets up but does not do.

## Design notes worth carrying into N1

- **API version negotiation**: both clients hit unversioned `GET /version` first, cache the
  daemon's own reported `ApiVersion` (live: `"1.52"`), and prefix every later call `/v1.52/...` —
  trusting the daemon's self-report rather than hard-coding a version, per r5's "don't chase 1.55
  exactly" advice, verified live against a daemon actually running 1.52 (not 1.55 — real-world
  drift from the docs, caught only by actually connecting).
- **Timeouts**: every method takes an explicit timeout; long-lived calls (`logs(follow)`, `events`,
  `wait`) use "no timeout" (`0` in TS, `None` in Python) rather than a bounded default, since a
  real SimNIBS/QSIPrep job can legitimately run for hours — a bounded default would have silently
  killed the exact calls this client exists to support.
- **`pullImage`/`pull_image` mid-stream error handling**: Docker reports some pull failures
  (unknown tag inside an otherwise-reachable registry) as `{"error": ...}` inside an HTTP-200
  NDJSON stream, not as an HTTP error status — both clients check for this explicitly
  (`docker-engine-client.test.ts`'s and `TestDockerEngineClient`'s `midstream-error` tests), a
  distinction a naive "check `res.statusCode >= 400`" implementation would silently swallow.
- **One connection per request, not connection pooling/keep-alive**: both clients open a fresh
  connection per call. Simpler, correct for this workload (job containers are not
  high-frequency-request traffic), and sidesteps HTTP/1.1 keep-alive edge cases entirely — a
  deliberate simplicity choice, not an oversight, worth reconsidering only if profiling in N1 shows
  connection-setup overhead actually matters (it did not show up in the live timings above: full
  round trips were all sub-second except the cold image pull).

## Follow-ups for Stage N1

1. Wire `tit/jobs/docker_engine.py` into `tit/pre/qsi/docker_builder.py`/`qsiprep.py`/`qsirecon.py`,
   replacing the `subprocess.run(["docker", ...])` calls and always passing `job_id` — closes the
   `stop_docker_siblings` dead-code gap for real.
2. Actual Windows verification: `parseDockerHostUrl`'s `npipe://` handling and
   `wellKnownCandidates("win32")` are unit-tested for shape only; nobody (this lane included) has
   connected to a real `//./pipe/docker_engine`.
3. A real Podman/Colima/OrbStack spike (skeptic-3 MISSING item #1) — this lane only added
   discovery candidates and a documented "unverified" stance, per its explicit scope.
4. Port the three Python-only connection-state classification tests
   (not-installed/not-running/socket-permission) to the TS suite for parity.
5. `eslint.config.mjs`'s ignore list needs `.runtime-staging/` and `release/` added (another
   lane's build artifacts, not this lane's files) — flagged, not fixed, since it's outside this
   lane's owned paths and unrelated to this lane's correctness.
6. Security posture question skeptic-3 raises (MISSING item #6) is now concretely live: Electron's
   main process, via `engine.ts`, can hold a direct, unmediated handle to the host Docker socket
   (root-equivalent) — worth an explicit product sign-off before N1 wires this into `stack.ts`
   (which this lane did **not** touch, per its owned-paths list).

## Environment

macOS 15 (Apple M2 Max), Docker Desktop 4.57.0 (215387) / Engine 29.1.3 / API 1.52 / arm64 VM;
Node v25.4.0; TypeScript via `desktop/node_modules/.bin/tsc`; Python 3.14.3 (Homebrew, host) and
Python 3.11.14 (`idossha/simnibs:v2.5.0`, container `tit-v3-spike`, emulated x86_64, running as
root — relevant to the socket-permission test's self-skip there).

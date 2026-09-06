# QA — staff engineer + security review (2026-09-03)

Reviewer pass over the v3 Docker-streamline program as built today. Scope per brief: (1) the
Engine API path in `desktop/src/main/{stack,docker/*}.ts`; (2) `/tetravox/` static route + CSP +
jail, `/api/files/raw`, iframe sandbox/postMessage trust model; (3) `tit/jobs/docker_engine.py` +
`tit/pre/qsi/docker_builder.py`; (4) CI/offscreen enforcement, secrets in logs. Time-boxed ~60
min. No repo files modified — one throwaway vitest file was added to prove finding #1 against the
real `composeFile.ts`/`compose.ts` code, run, and deleted before this note was written (`desktop/`
is entirely untracked in this worktree's git — confirmed via `git ls-files desktop | wc -l` → 0 —
so there was nothing to leave dirty either way).

Read: `dev/notes/v3-docker-streamline-plan.md` (D1–D6, §1 contracts), all eight lane notes in this
directory, `desktop/DESIGN.md` §8.1/§10, both `viewer-real-embed*.png` screenshots. Live checks ran
against the maintainer's own stack container (`ti-toolbox-fad740e5-tit-1`, read-only: `curl` +
`docker inspect`/`docker logs`, never started/stopped/jobbed) and pure-function unit tests against
the real desktop source — no scratch container was needed for this lens.

## Findings

### 1. BLOCKER — every stack start bind-mounts a host directory over the image's own `/ti-toolbox`, unconditionally, undermining D1

`desktop/src/main/stack.ts:456-458`:

```ts
function resolveRepoDir(): string {
  return process.env.TIT_DEV_REPO_DIR || join(app.getAppPath(), "..");
}
```

`startFresh()` (same file, line 247) calls this **unconditionally** — `repoDir: resolveRepoDir()`
— and `buildStackEnv()` (`desktop/src/shared/compose.ts:116`) sets `TIT_REPO_DIR` whenever
`repoDir` is truthy. `resolveRepoDir()` can never return an empty string: absent
`TIT_DEV_REPO_DIR`, it falls back to `app.getAppPath() + "/.."`, which is always a real path.
There is no `app.isPackaged` check anywhere in `desktop/src` (`rg -n "isPackaged" desktop/src` →
zero hits).

The shipped compose file (`desktop/docker/docker-compose.v3.yml:54`) mounts it unconditionally too
— `${TIT_REPO_DIR}:/ti-toolbox`, no `:-` default — even though the file's own header comment (line
36-38) and W2's/W4's lane notes both describe this as "the optional dev-repo mount, omitted when
`TIT_REPO_DIR` is unset." **`TIT_REPO_DIR` is never unset.** `working_dir: /ti-toolbox` is also the
directory the image's baked-in `tit` package and entrypoint live under (D1: "the built desktop UI
at `/opt/ti-toolbox/ui`... `tit` baked in").

Verified against the real code (not a hypothetical): a temporary vitest test imported the actual
`parseComposeFile`/`buildContainerPlan` (`shared/composeFile.ts`) and `buildStackEnv`
(`shared/compose.ts`) against the real `docker-compose.v3.yml`, with `repoDir` set to what
`resolveRepoDir()` would produce for a packaged macOS app (`app.getAppPath()` under
`Contents/Resources`, i.e. `/Applications/TI-Toolbox.app/Contents/Resources`):

```
buildStackEnv output has TIT_REPO_DIR: /Applications/TI-Toolbox.app/Contents/Resources
HostConfig.Binds: [
  "/Users/someone/data/000:/mnt/000",
  "/Users/someone/.config/ti-toolbox:/root/.config/ti-toolbox",
  "/var/run/docker.sock:/var/run/docker.sock",
  "/Applications/TI-Toolbox.app/Contents/Resources:/ti-toolbox"
]
```

A second assertion in the same test confirms the only way to *not* get that bind is to omit
`TIT_REPO_DIR` from the env passed to `parseComposeFile` entirely — which throws
(`compose: ${TIT_REPO_DIR} is not set`) rather than omitting the volume, so nothing in the current
code path can reach "no dev-repo mount" short of editing the shipped compose file by hand. (Test
file was `desktop/tests/unit/_qa_repo_mount_check.test.ts`; run, its output captured above, then
deleted — see header.)

**Impact.** `Contents/Resources` (a packaged app's own bundle directory) has no `tit/` Python
package in it — it is `out/**`, `package.json`, and whatever `electron-builder.yml`'s
`extraResources` copies (today: only `runtime/` and `renderer/`, for the unrelated N0.4 native
spike). Bind-mounting it over the container's `/ti-toolbox` would delete the image's own baked-in
`tit` tree for the container's lifetime, and `simnibs_python -m tit.server` would fail with
`ModuleNotFoundError: No module named 'tit'` at the very first packaged-Docker-mode launch. D1's
whole premise ("the installation should be shipped within the docker... SimNIBS 4.6 + `tit`... +
FastSurfer... baked in") is silently defeated by this mount every single time the app starts a
stack, dev or (eventually) packaged — today it only *looks* correct because
`app.getAppPath()/..` in every tested configuration (`npm run dev`, the e2e harness) happens to
equal the repo root, which does contain a real `tit/`. **This exact bug is the reason W2's smoke
test (`w2-image-notes.md`) had to work around a "stale `tit/viewspec.py` from a concurrently-edited
worktree" — that was this same unconditional host bind-mount, observed from the other side.**

This has never been caught because `desktop/electron-builder.yml` has no packaging path for the
Docker-centric product at all yet (see finding #8) — the landmine is real but has not detonated
because nobody has packaged a Docker-mode build to step on it.

**Fix.** Gate `resolveRepoDir()`'s fallback on `!app.isPackaged` (return `undefined`/`null` when
packaged and `TIT_DEV_REPO_DIR` is not explicitly set), and change `buildStackEnv` /
`docker-compose.v3.yml` so an absent `TIT_REPO_DIR` genuinely omits the bind — either give the
compose line a `${TIT_REPO_DIR:-}` default and have `composeFile.ts`/`buildContainerPlan` special-
case an empty-string volume source by dropping that bind entry (exactly what W2's own note asked
W4 to do — it was not done), or split the compose file so the dev mount is not part of the shipped
"production" definition at all.

### 2. HIGH — the desktop app has zero CI enforcement; `npm run e2e:quiet` and the offscreen invariant are never run outside a developer's own machine

`.circleci/config.yml` (228 lines) defines exactly two jobs, `build-and-smoke-image` and
`build-and-run-tests` (`grep -n "^jobs:\|^  [a-z-]*:$"` → lines 25/49/145); neither runs `npm`,
`vitest`, `playwright`, or anything under `desktop/`. The only mention of `desktop` in the whole
file is a comment (line 61): `# built desktop UI bundle, which is desktop's own vitest/build/e2e
gates'` — describing gates that are not actually wired into this pipeline anywhere.

This means: `npm run typecheck`, `npm run lint`, `npx vitest run`, `npm run build`, and — the gate
this whole security lens depends on, DESIGN.md §8.1's "it is proven, not asserted" claim —
`npm run e2e:quiet` are exercised **only** when a lane agent or developer happens to run them by
hand in a given session. Every "16 passed / no Electron window reached the screen" result cited
across the eight lane notes in this directory is real for that session, but nothing stops the next
commit from silently breaking the offscreen guarantee, the IPC gating (`fromLauncherWindow`), or
any of this review's other findings from ever being re-verified.

**Fix.** Add a `desktop` CI job (Linux executor) running `npm ci`, `npm run typecheck`, `npm run
lint`, `npx vitest run`, `npm run build`, and `npm run e2e:quiet`, wired into the same workflow as
the two existing jobs. Playwright launches Electron `TIT_E2E_OFFSCREEN=1` (never actually shown),
but Electron's own GPU/window-server init on a headless Linux CI box still typically needs
`xvfb-run` as a stability net even for a window that is never `.show()`n — confirm whether the
`ubuntu-2204:current` machine image already provides a display, and wrap the step in `xvfb-run` if
not.

### 3. HIGH — the bearer token is readable via `docker inspect`/`docker exec ... env` by any local principal with Docker socket access, a wider blast radius than the file it replaced

Confirmed live against the maintainer's real running container:

```
$ docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep TOKEN
TIT_SERVER_TOKEN=DHi-_PtUC0PsJyaYAYVhtMxLGbubhbc04Eo749RONZg
```

`stack.ts`'s `tryAttach()` (line 219) reads this same value back out of `Config.Env` on every
attach — by design, it is the only place the token lives (`w4-desktop-docker-notes.md`: "the token
never has to be written to the host filesystem at all"). The design note frames this purely as a
benefit (no `stacks.json`, survives a cleared `userData` dir) and flags only a generic "security
posture... worth an explicit sign-off" follow-up — it does not name this specific trade-off.

**Why it matters.** The previous file-based design stored this token in a `0600` file under the
app's own `userData` directory — readable only by the OS user running the app. `docker inspect`
(and `docker exec <container> env`, and reading `/proc/<pid>/environ` for the entrypoint process)
are readable by **any member of the local `docker` group**, not just the app's own OS user. On a
single-user desktop this is a wash (Docker socket access is already root-equivalent). On a
**shared multi-user Linux host** — a plausible deployment for a lab workstation where several
accounts are conventionally added to `docker` for convenience — this is new: user B, who has never
been granted anything about user A's project, can `docker inspect` user A's running
`ti-toolbox-*` container, read the token, and since the server is bound to `127.0.0.1` (reachable
by every local user on that same host, not just A), immediately read/browse/run jobs against A's
project data with A's own credentials. That is a real, not merely theoretical, cross-user
disclosure this rewrite introduces.

**Fix / proposal.** At minimum, document this trust boundary explicitly (installation docs already
say nothing about `docker`-group membership implying access to other users' running TI-Toolbox
sessions on a shared host) so an admin setting up a shared box knows not to add mutually-untrusted
users to the same `docker` group. If tightening the blast radius is wanted: rotate the token on
each `tryAttach` (short-lived), or keep the container-env approach but additionally require the
connecting client to prove host-side knowledge unavailable to a mere `docker inspect` (e.g. a
value written to a file under the *invoking user's* `userData` dir at container-create time,
readable only by that OS user, checked in addition to the env-derived token on attach).

### 4. MEDIUM — `HEAD /` (every UI page) returns 405, unlike `/tetravox/*` which lane R2 already fixed for parity

```
$ curl -sI -X HEAD http://127.0.0.1:8765/
HTTP/1.1 405 Method Not Allowed
allow: GET
```

`tit/server/static.py:128`, the SPA catch-all `serve()`, is registered only as
`@router.get("/{path:path}", ...)`. R2's own fix for `/tetravox` (item 7 in `r2-fixup-notes.md`)
added matching `@router.head(...)` decorators for exactly this reason ("FastAPI's `APIRoute` does
not infer HEAD from GET the way a plain Starlette `Route` does") but the same treatment was never
applied to the main SPA route this brief also asked about. Low practical impact (nothing in this
app currently issues `HEAD /`), but it is one of the explicit checks in this review and a one-line,
mechanical fix: add `@router.head("/{path:path}", include_in_schema=False)` above `serve`.

### 5. MEDIUM — `computeProjectName`'s 32-bit hash is the sole cross-project discovery/attach key; a collision silently attaches one project's UI to another project's container

`desktop/src/shared/compose.ts`: `computeProjectName(dir) = "ti-toolbox-" + hash8(dir)`, and
`hash8` is explicitly documented as "a small, stable, **non-cryptographic** 32-bit hash... nothing
here is a security boundary, just a short deterministic project-name suffix." But
`stack.ts::tryAttach` uses exactly this value — the `tit.project` label — as the *entire* match key
for "is there already a running stack for this directory": `api.listContainers({[LABEL_PROJECT]:
projectName})`, then attaches to whatever it finds, reading its port/token straight out of that
container's env. Two distinct project directories whose paths happen to hash to the same 8 hex
chars (32-bit space; ~50% collision probability past roughly 77,000 distinct directories ever
opened on one machine by the birthday bound, and a single accidental collision could occur far
earlier) would attach to and share a single container — user opens project B, gets project A's
data/token back, silently. `tests/unit/compose.test.ts` tests `hash8`'s determinism and shape
(`/^[0-9a-f]{8}$/`) and that two different inputs it happens to try differ — it does not, and by
construction cannot, test collision-freedom.

**Fix.** Either widen the hash (64+ bits removes the practical risk) or make attach compare the
resolved `tit.host_project_dir` label (already stored, `LABEL_HOST_DIR`) against the actual
requested `hostProjectDir` before trusting an attach, not only the `tit.project` label — cheap,
and turns a silent cross-project attach into a clean "stale container found, recreating" path
instead.

### 6. MEDIUM — quitting with no jobs running leaves the container running forever with no notice, and there is no in-app way to stop it once connected

`desktop/src/main/index.ts:335-353`, `handleQuitRequest`:

```ts
const current = stack.getCurrent();
if (current) {
  const count = await getRunningJobsCount();
  if (count > 0) { /* ...dialog... */ }
}
// falls straight through to quitGate.approve(); proceed(); when count === 0
```

When zero jobs are running, the function never asks and never calls `stack.stop()` — the container
keeps running, holding the `docker.sock` bind mount and consuming host CPU/RAM, with nothing on
screen telling the user this happened. This may be an intentional trade-off for instant reattach
(the "attach, don't kill" design the whole rewrite is built around), but it is not documented
anywhere as a decision, and there is no way to reverse it short of a terminal `docker stop` —
confirmed by grep: `stack:stop` is invoked from exactly two places in the whole renderer/main tree
(the launcher's own Stop button, and this quit dialog's "Stop containers and quit" choice), both
gated to `fromLauncherWindow`; once the window has navigated to the connected server's own origin
there is no "Stop stack"/"Disconnect" affordance anywhere in `src/renderer` that could reach it.

**Fix.** Either add a visible "Stop Docker stack" action reachable from the connected app
(Settings, or the System/Jobs page), or at minimum show a persistent notification/toast on quit
("TI-Toolbox is still running in the background — N GB RAM") regardless of whether jobs are
active, so the behavior is discoverable rather than silent.

### 7. LOW — `tit/pre/qsi/docker_builder.py` still shells out to the `docker` CLI (documented gap, not fixed here); `docker_engine.py`'s own docstring about labels is now stale

`rg -n '"docker"' tit/pre/qsi/docker_builder.py` → lines 217 and 319 (both inside `subprocess`-
style argv construction for the QSIPrep/QSIRecon sibling containers) — this is the one CLI use D4
says should not exist ("nothing shells out to `docker`... beyond `docker context inspect`" is the
*desktop* client's rule; the *server-side* `tit/jobs/docker_engine.py` Engine API client exists
specifically to replace this, per its own docstring, but is "not wired into
`tit/pre/qsi/*.py` yet; that integration is out of scope for this spike"). Both `w2-image-notes.md`
(follow-up #5) and `w3b-preprocessing-notes.md` already flag this as open — confirmed still true.

Separately: `tit/jobs/docker_engine.py`'s module docstring claims *"today no builder in
`tit/pre/qsi/docker_builder.py` ever sets this label (confirmed: `rg -n "tit\.job_id"
tit/pre/qsi/docker_builder.py` has zero hits)"* — that is no longer true. `docker_builder.py`'s
`_label_args()` (lines 137-154, credited to "N0.6 spike") **does** set `tit.job_id` on both the
`qsiprep` and `qsirecon` `docker run` invocations (lines 224 and 326). The label gap the docstring
describes has already been closed by a later change; the docstring was not updated to match. Low
severity (comment-only), but worth a one-line fix so the next reader isn't misled into re-fixing an
already-fixed problem.

### 8. LOW (tracking gap, not a bug in isolation) — `electron-builder.yml` has no packaging path for the Docker-centric product yet

`desktop/electron-builder.yml`'s own header: *"electron-builder config for the N0.4
native-packaging spike... NOT a production release pipeline."* Its `extraResources` copies only
`runtime/<platform-arch>` (the native-runtime spike's bundled Python) and `renderer/`; nothing
copies `docker/docker-compose.v3.yml` anywhere `stack.ts::resolveComposeFile()`'s
`process.resourcesPath` candidate would find it. This means finding #1 has literally never been
exercised against a real packaged build — flagging so Phase-C packaging work picks it up before
shipping, not after.

### 9. Verified false-positive, noted for the record — path traversal on `/api/files/raw` is correctly blocked; my first test was misleading due to curl's own URL normalization

First pass, without `curl --path-as-is`:

```
$ curl -s -b cookies.txt -o /dev/null -w "%{http_code}\n" \
    "http://127.0.0.1:8765/api/files/raw/mnt/../../../../etc/passwd"
200
```

That "200" is **not** a server-side traversal — curl itself collapses `/mnt/../../../..` client-
side per RFC 3986 §5.2 before ever sending the request, so the actual wire request was `GET
/etc/passwd HTTP/1.1`, which the SPA catch-all correctly served as `index.html` (nothing under
`/etc` is `api`/`ws`/`auth`/`tetravox`, so it falls through to the SPA fallback — expected
behavior, not a vulnerability). Re-tested with `--path-as-is` (send the literal path, no
normalization) against both the raw and artifact routes:

```
$ curl -s --path-as-is -b cookies.txt "http://127.0.0.1:8765/api/files/raw/mnt/../../../../etc/passwd"
{"detail":"Path escapes the project jail"}   # 403
$ curl -s --path-as-is -b cookies.txt -o /dev/null -w "%{http_code}\n" \
    "http://127.0.0.1:8765/api/files/artifact?path=/mnt/../../../../etc/passwd"
403
```

Both correctly refuse. URL-encoded variants (`..%2f..%2f..%2fetc%2fpasswd`,
`%2e%2e%2f%2e%2e%2fetc%2fpasswd`) also 403. Recording this explicitly because a hasty single-request
test (the kind a less careful pass would stop at) would have misreported a live traversal bug that
does not exist.

## What is good (verified, not just read)

- **Token masking in logs is real, not just implemented.** Grepped the maintainer's live container
  log after exercising `/auth/session?token=...` and the jobs WebSocket myself:
  `GET /auth/session?token=*** HTTP/1.1`, `WebSocket /ws/jobs?token=***` — `TokenMaskFilter`
  (`tit/server/access_log.py`) is wired onto both uvicorn handlers (`__main__.py`) and works.
  Desktop-side, `index.ts`'s `stripQueryForLog` is applied to every URL the main process logs, with
  a specific comment calling out the one `did-fail-load` call site that would otherwise leak the
  token verbatim (ra_14 finding 8) — grepped the rest of `src/main` for any other `log(...token...)`
  call site; none found.
- **`/api/files/raw` and `/api/files/artifact` correctly jail traversal** (see finding #9) — plus
  `O_NOFOLLOW` on the raw route's final `open()` closes the symlink-swap TOCTOU window that the
  artifact route still has, and that gap is explicitly documented in the raw route's own comment
  rather than silently present, so it reads as a known, scoped limitation, not an oversight.
- **`fromLauncherWindow` correctly narrows the dangerous IPC surface.** `stack:start`, `stack:stop`,
  `selectDirectory`, and `setSettings` all require both same-window *and* the sender frame's URL
  being the local `app://launcher` page — a compromised/malicious page served by `tit.server`
  itself (which is same-origin with the connected app, and therefore has full `fromMainWindow`
  access to `openPath`/`showItemInFolder`/`selectFile`/`notify`) cannot reach `stack.start`,
  `stack.stop`, or pick a new host directory. Confirmed by reading `registerIpc()` end to end; no
  handler that touches the Docker socket or an unjailed host path is missing the launcher check.
- **The iframe trust model is sound and its `allow-same-origin` reasoning holds up.**
  `acceptEmbedMessage` (`viewer/protocol.ts:538`) checks **both** `event.origin === hostOrigin`
  **and** `event.source === frame.contentWindow` — closing exactly the gap an origin-only check
  would leave (a same-origin sibling iframe posting spoofed messages), which the code's own comment
  calls out by name.
- **The compose parser's strict subset and forced-loopback ports are real guardrails, not
  decoration.** `parsePort` refuses anything but `127.0.0.1`/`localhost`/`::1` as the bind host
  (`compose: ... only 127.0.0.1 is allowed`) and every unknown top-level/service/healthcheck/
  network/volume key is a named `StackError`, not a silent drop — verified by reading
  `composeFile.ts` end to end against the actual shipped `docker-compose.v3.yml`.
- **Podman is fingerprinted and refused with a clear message**, not silently misbehaving under
  emulation or a mismatched API — `isUnsupportedEngine` checks the daemon's own self-reported
  `Components`/`Platform`/`Version` text for "podman" before any container is created.

## Not reached in the time-box

- Windows named-pipe path (`docker/discover.ts`'s `npipe://` handling) — no Windows machine
  available; already honestly marked `UNVERIFIED` in the source itself, nothing new to add.
- A real end-to-end packaged-Docker-mode launch (blocked on finding #8 — the packaging config for
  this product doesn't exist yet, so there is nothing to launch).
- `tit/jobs/docker_engine.py` was read (docstring, discovery, framing) but not exercised live —
  it is not yet called from any production code path (confirmed dead-but-intentional via its own
  docstring), so there was nothing running to test against.

# W4 — Desktop: the stack through the Engine API, compose as the definition, X11 gone

Phase A, lane W4 of `dev/notes/v3-docker-streamline-plan.md`. Everything below is either a file I
wrote, a command I ran with its real output, or a thing I deliberately did not do and why.

## What the stack is now

```
stack.start(projectDir)
  discover()                       docker/discover.ts — DOCKER_HOST, then `docker context inspect`,
                                   then well-known sockets. The ONLY CLI use left in the app.
  client.version()                 min API 1.41 (the `?platform=` query on container create);
                                   a Podman-flavoured /version is refused by name.
  parseComposeFile(text, env)      shared/composeFile.ts — the plan §1 subset, ${VAR} interpolation,
                                   unknown key -> StackError naming it.
  buildContainerPlan(stack, …)     -> container name, image+tag, platform, network name, volume
                                   names, published port, and the POST /containers/create body.
  ensureNetwork / ensureVolume     docker/stackApi.ts
  imageExists ? skip : pullImage   NDJSON progress -> formatPullEvent -> the same launcher line
                                   the CLI used to print ("a1b2c3d4 Downloading 25%").
  createContainer(?name,?platform) labels tit.project / tit.stack / tit.service / tit.host_project_dir
  startContainer                   then stream the container's own log lines to the launcher
  waitForServer                    /api/health raced against "did the container exit" (400 ms poll)
  -> { url, token }
```

`stop()` = stop (10 s grace) + remove; named volumes are kept. `status()` = inspect.

**Attach-or-start is by label, and there is no `stacks.json` any more.** `listContainers({tit.project})`
finds this project's container; `inspect` reads its port and bearer token out of *its own
environment*. That deleted `src/main/stackState.ts` outright: the token no longer has to be written
to the host filesystem at all (the old file was 0600 precisely because it held one), and attach now
survives a lost/cleared `userData` directory, which the file-based version did not.

## Files

| Added | |
|---|---|
| `desktop/src/shared/composeFile.ts` | compose subset parser + `buildContainerPlan` (pure; no `node:*`/electron, so it type-checks and runs under both tsconfigs) |
| `desktop/src/main/docker/stackApi.ts` | the endpoints `engine.ts` lacks: `listContainers`, `createContainer` with `?name=&platform=`, `inspect` (health, ports, env), `removeContainerById`, `imageExists`, `ensureNetwork`, `ensureVolume` |
| `desktop/tests/unit/composeFile.test.ts` | 33 tests: interpolation, binds, ports, durations, shlex, every unsupported-key path, the plan build |
| `desktop/tests/unit/docker-stack.test.ts` | 10 tests: `StackApi` against the fake Engine API |
| `desktop/tests/e2e/fixtures/compose-v3.fixture.yml` | mirrors W2's file while it is being written (see Contracts) |

| Rewritten | |
|---|---|
| `desktop/src/main/stack.ts` | 247 -> 460 lines, all Engine API; no `execFile`, no X11, no compose CLI |
| `desktop/src/shared/compose.ts` | kept `generateToken`/`hash8`/`computeProjectName`/`buildStackEnv` (minus `DISPLAY`, `FREESURFER_VOLUME`); the compose-CLI arg builders and `classifyDockerError` are replaced by label constants and `stackErrorMessage` |
| `desktop/src/shared/pullProgress.ts` | added `formatPullEvent` — NDJSON object -> the existing `ParsedProgressLine`, so the launcher UI is untouched |
| `desktop/tests/e2e/fixtures/fake-engine-api.mjs` | + image inspect, networks, volumes, label-filtered container list, `?name=`/`?platform=`, rich inspect, a request log, and an opt-in in-process "tit.server" that listens on the started container's own `TIT_SERVER_PORT` |
| `desktop/tests/e2e/launcher.spec.ts` | 9 tests against the fake Engine API instead of a fake `docker` binary |
| `desktop/tests/unit/compose.test.ts`, `pullProgress.test.ts` | follow the above |

| Deleted | why |
|---|---|
| `desktop/src/main/x11.ts` (200 lines) | D3 — no X11 in the product |
| `desktop/src/main/dockerCli.ts` (189 lines) | D4 — nothing shells out to `docker` any more |
| `desktop/src/main/stackState.ts` (69 lines) | the container is the source of truth (above) |
| `desktop/tests/e2e/fixtures/fake-docker.js` (176 lines) | there is no CLI left to fake |

Also gone: the X11 revert in `index.ts`'s quit path, `CurrentStack.revertX11`, `TIT_SKIP_X11`,
`buildStackEnv`'s `DISPLAY`/`freesurferVolume`, and the `freesurfer` service/volume handling
(the parser refuses the legacy file by name rather than silently dropping it).

`desktop/package.json` gained exactly one dependency, `yaml@2.9.0` (`npm install yaml@2.9.0
--save-exact`; the lockfile diff is that package and nothing else).

## Decisions worth arguing with

1. **Two clients over one connection.** `docker/{discover,engine,frames}.ts` are frozen as N0.3
   delivered them, so the endpoints they lack went into a new `docker/stackApi.ts` with its own
   ~60-line request helper. `stack.ts` holds both: `DockerEngineClient` for the streaming pieces
   already proven live against Docker 29.1.3 (`pullImage`, `logs`, start/stop/remove) and `StackApi`
   for the rest. Folding them into one client with one helper is the obvious cleanup once those
   files are unfrozen — it is duplication I chose over editing another lane's files.
2. **`platform` and `restart` are two additions to plan §1's key list**, both honoured, not ignored.
   `platform` is load-bearing: the image is `linux/amd64` and the daemon ignores a `Platform` field
   in the create *body*, so it has to be the `?platform=` query. `restart` maps onto
   `HostConfig.RestartPolicy`. Everything else outside the list is a `StackError` naming the key.
3. **A port mapping without an explicit `127.0.0.1` is a parse error**, not a silent rewrite
   (TODO §2.8). `"8765:8765"` and `"0.0.0.0:8765:8765"` both fail with the key named.
4. **An unset `${VAR}` with no default is an error**, not an empty string. Every variable the
   shipped compose file uses is one the app itself supplies, so a missing one is a bug in the app —
   and mounting `""` or publishing port `""` is the worst possible way to report it.
5. **Health is raced against "did the container exit".** A container that dies two seconds in (bad
   mount, missing entrypoint) would otherwise sit on "waiting for the server" for the full 120 s
   timeout and then report the wrong cause. Caveat: with `restart: unless-stopped` and a *real*
   daemon, a crash-looping container flips between exited and running, and this reports the first
   exit it sees. That is the right answer — a crash-loop never serves — but it is why I would rather
   the shipped file not set a restart policy (see Contracts).
6. **`client.events()` is not wired.** Container log lines already give the launcher what it needs
   during startup, and a `/events` stream would duplicate the exit poll. It stays available for
   whoever wants desktop-side reaction to `container/die` after startup.

## Error UX

`stackErrorMessage(kind, detail?)` in `shared/compose.ts` — one message per kind, all distinct
(asserted by a test that compares the set size):

| kind | copy |
|---|---|
| `not-installed` | "Docker was not found on this machine. Install Docker Desktop (macOS/Windows) or Docker Engine (Linux)…" |
| `not-running` | "Docker is installed but not running. Start Docker Desktop (or your Docker daemon)…" |
| `socket-permission` | "…add your user to the docker group (sudo usermod -aG docker $USER), then log out and back in. On macOS, restart Docker Desktop." |
| `unsupported-engine` | "…TI-Toolbox needs Docker Desktop or Docker Engine; Podman is not supported." |
| `image-pull-failed` | "The TI-Toolbox image could not be downloaded…" |
| `health-timeout` | "The container started but its server never answered…" |
| `container-exited` | "The container exited while starting up. (exit code N …)" |
| `compose-invalid` | "The stack definition could not be read. (<the key at fault>)" |

`detail` is appended in parentheses when there is one and omitted entirely when there is not (no
empty `()`).

## Gates

```
$ npx tsc --noEmit -p tsconfig.web.json
(exit 0, no output)

$ npx tsc --noEmit -p tsconfig.node.json
tests/mock-server/contract.test.ts(32,5): error TS2578: Unused '@ts-expect-error' directive.
   ^ NOT this lane's file (W3a owns tests/mock-server/**) and NOT this lane's code: that line is
     `// @ts-expect-error -- optional: only used if the `yaml` package happens to be installed`,
     and this lane installed it. One-line fix, for W3a — see "Needs from other lanes".

$ npm run lint
✖ 3 problems (0 errors, 3 warnings)
   ^ all three pre-existing react-hooks/incompatible-library warnings in src/renderer/ui/
     (DataTable.tsx, VirtualList.tsx) and pages/preprocess — untouched by this lane.
$ npx eslint src/main src/shared src/preload tests/unit tests/e2e/launcher.spec.ts tests/e2e/fixtures/fake-engine-api.mjs
(exit 0, no output — every file this lane owns)

$ npx vitest run
 Test Files  45 passed (45)
      Tests  461 passed (461)      # was 43 files / 418 tests before this lane

$ npm run build
✓ built in 2.24s                   # and `grep -o 'require("yaml")' out/main/index.js` -> present,
                                   # i.e. electron-vite externalised the new dependency correctly

$ TIT_E2E_RUN_ID=w4-$RANDOM bash scripts/e2e-quiet-check.sh \
    npx playwright test tests/e2e/launcher.spec.ts tests/e2e/smoke.spec.ts
  16 passed (58.3s)
e2e-quiet-check: frontmost after  = Tetravox   (85 samples)
e2e-quiet-check: no Electron/Chromium window reached the screen.
e2e-quiet-check: PASS
```

The nine launcher tests: fresh start (asserting the network, the volume, the labels, the
`linux/amd64` platform, the loopback-only port binding, the project bind, the healthcheck, that
nothing mentions X11, that the pull happened before the create); attach without a second container;
stop that removes the container and keeps the volume; an already-present image that is never pulled
(`fake.requests` has no `POST /images/create`); the launcher-only IPC refusals; the
`openPath`/`showItemInFolder` jail; Docker-missing / Podman / pull-failure each with their own
message; a container that exits during startup reporting *that*, with its exit code; and the
launcher UI's own Browse + Start buttons.

## Contracts for W2 (the compose file)

`desktop/tests/e2e/fixtures/compose-v3.fixture.yml` is what this lane codes against — it is a
working file, so it is also the cheapest specification. The parser accepts exactly:

```
services.<name>.{image, environment, volumes, ports, labels, healthcheck, command, working_dir,
                 init, platform, restart, networks}
healthcheck.{test, interval, timeout, retries, start_period, disable}
networks.<name>.{name, driver}      volumes.<name>.{name}      top level: services, networks, volumes
                                    (top-level `version:` is accepted and ignored — it is a no-op)
```

Anything else — `depends_on`, `tty`, `stdin_open`, `env_file`, `external`, long-form volume syntax —
is a startup error naming the key, by design. Three hard requirements:

1. `ports:` must be `"127.0.0.1:${TIT_SERVER_PORT}:${TIT_SERVER_PORT}"`, exactly one entry.
2. `environment:` must carry `TIT_SERVER_PORT` and `TIT_SERVER_TOKEN` — attach reads them back out
   of the running container.
3. The variables the app supplies are exactly `LOCAL_PROJECT_DIR`, `PROJECT_DIR_NAME`,
   `TIT_USER_CONFIG`, `TIT_HOST_OS`, `TIT_HOST_OS_VERSION`, `TIT_HOST_ARCH`, `TZ`,
   `TIT_SERVER_PORT`, `TIT_SERVER_TOKEN`, plus `TIT_REPO_DIR` and `TIT_STATIC_DIR` (dev only —
   give anything else a `${VAR:-default}`).

Recommendation, not a requirement: **drop `restart:` from the shipped file.** The app owns the
container's lifecycle; a restart policy only adds "comes back after a daemon restart" and turns a
boot crash into a loop. The parser supports it either way.

`tests/unit/composeFile.test.ts` already parses the shipped file: while it still declares
`freesurfer:` the test asserts the parser refuses it by name; the moment W2's rewrite lands the same
test asserts it parses into a single `tit` service on loopback with no X11 and builds a plan. No
edit needed on this side.

## Needs from other lanes

- **W3a**, `desktop/tests/mock-server/contract.test.ts:32` — delete the now-stale directive (the
  `yaml` package is installed, so the import no longer errors and `tsc` flags the unused
  suppression). While you are there the `try`/`catch` python3 fallback below it is now dead too,
  though harmless.

  ```diff
  -    // @ts-expect-error -- optional: only used if the `yaml` package happens to be installed
       const { parse } = await import("yaml");
  ```

- **W3a / W5**, capabilities: `x11_display`, `freeview`, `gmsh` are gone from the product. The
  desktop side no longer produces or consumes them; `desktop/tests/e2e/viewer.spec.ts:63,80,83`
  still stubs `x11_display` and `freesurfer` in a capabilities fixture (W5's file).
- **Whoever unfreezes `docker/{discover,engine,frames}.ts`**: their header comments still describe
  `dockerCli.ts` as "unchanged" and reference `TIT_DOCKER_BIN`; that file is deleted.
  `src/main/nativeRuntime.ts:11` still cross-references the deleted `stackState.ts`.

## Follow-ups

1. Fold `docker/stackApi.ts` into `docker/engine.ts` (one client, one request helper) once the N0.3
   files are unfrozen.
2. Windows named pipe: still never connected to (N0.3's open item, unchanged here). The app's whole
   stack path now depends on it.
3. `TIT_STACK_HEALTH_TIMEOUT_MS` overrides the 120 s startup health timeout; only the default is
   exercised. A first real amd64 pull-and-boot on a cold machine should be timed against it.
4. Security posture (skeptic-3 MISSING #6) is now fully live: main holds an unmediated handle to the
   host Docker socket, and `stack.start` is reachable only from the launcher page (`fromLauncherWindow`).
   Worth an explicit sign-off before shipping.
5. `client.events()` remains unused (decision 6 above).

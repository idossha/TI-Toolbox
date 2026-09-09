# TI-Toolbox desktop

Electron shell + React renderer for TI-Toolbox v3. The renderer bundle (`out/renderer`) is what
`tit.server` serves at `/`; every request it makes is origin-relative (`/api/...`, `/ws/system`),
so the same bundle works inside Electron, in the Vite dev server (proxied) and in browser mode.
The Electron main process only does host things: a local launcher page, a health poll, a
navigation guard and a settings file. Science and path rules stay in Python (`tit`).

Development guide: [CONTRIBUTING](../docs/dev/CONTRIBUTING.md), design contract:
[DESIGN](../docs/dev/DESIGN.md), API contract: [OpenAPI](../contracts/openapi.yaml)
(see [contract workflow](../contracts/README.md)).

## Layout

```
electron.vite.config.ts   main / preload / renderer builds; dev proxy for /api /auth /ws
scripts/dev*.ts           `npm run dev` / `dev:web` / `dev:down`: .env.dev, attach-or-start the
                          container through src/main/stack.ts, the bearer+Origin proxy factory
src/main/                 app lifecycle, launcher page (app://launcher), connect + nav guard, log, settings
src/main/stack.ts         attach-or-start, electron-free (an injected StackHost); stackHost.ts binds
                          the Electron half, so scripts/dev.ts runs the same code under Node
src/preload/              contextBridge `window.tit` (sandboxed, dependency-free)
src/shared/tit-bridge.d.ts  the bridge's TypeScript surface (renderer + preload)
src/renderer/
  ui/          design system — tokens.css/base.css/components.css + every primitive (docs/dev/DESIGN.md §5);
               pages import only from here, never a literal colour
  forms/       schema loader (/api/schema, cached), Ajv 2020-12 react-hook-form resolver, SchemaField,
               server-error -> field mapping (see forms/README.md)
  app/         shell: nav rail, top bar, page registry (pages/*/index.tsx, auto-discovered), jobs
               store + rail (app/jobs/README.md), theme store, keyboard shortcuts, memory router
  pages/       one directory per screen; each exports a `PageDef` and owns its own tests/e2e/<name>.spec.ts
  dev/Gallery.tsx  every primitive, every state — see "Design gallery" below
  api/, ws/    openapi-fetch client + generated schema.d.ts; /ws/system client
tests/unit/               vitest (API wrapper, WS reconnect with fake timers, useSystemStream in jsdom)
tests/e2e/                Playwright driving the BUILT Electron app (smoke, gallery, one spec per page)
tests/mock-server/        mock tit.server from tests/fixtures (port 8790) + its parity test (logout, WS origin)
```

## Design gallery

`dev/Gallery.tsx` (page id `dev`) renders every design-system primitive in every listed state, with
a light/dark toggle, for design QA screenshots (`tests/e2e/gallery.spec.ts`). It is excluded from a
normal build:

- `npm run dev` / `electron-vite dev` — included whenever `import.meta.env.DEV` is true (always, in
  the dev server).
- `npm run build` (plain `electron-vite build`) — **excluded**. `import.meta.env.DEV` is false here.
- `npm run e2e` (`pree2e` → `VITE_INCLUDE_GALLERY=1 VITE_SCENE_HOOKS=1 electron-vite build`) —
  **included**, via that env var, so the gallery can be screenshotted against a real
  production-shaped build.

`VITE_SCENE_HOOKS=1` is a **separate** flag with the same mechanism, and it gates the run-page
scene test seam (`window.__scenePane` — `SCENE_DEBUG` in `pages/_shared/scene/ScenePane.tsx`) rather
than the gallery page. They were one flag until 2026-09-04; splitting them means a
`--project=real` scene spec no longer has to build a `dev/` route it never opens, and a build made
without the flag fails with a missing hook instead of a missing gallery heading.

Gotcha: `electron-vite build`'s CLI accepts `--mode <mode>`, but its build command hardcodes
`process.env.NODE_ENV = 'production'` internally regardless of `--mode` (see
`node_modules/electron-vite/dist/chunks/lib-*.js`, `resolveConfig(inlineConfig, 'build', 'production')`)
— so `import.meta.env.DEV`/`PROD` (which key off `NODE_ENV`, not `MODE`) are always
`false`/`true` for any `electron-vite build`, `--mode` or not. `VITE_INCLUDE_GALLERY` sidesteps this
by using Vite's separate `VITE_`-prefixed env-var inlining instead of the mode/NODE_ENV machinery.

## Commands

```bash
npm install                 # Electron 44.0.0 (pinned) is downloaded from GitHub on install
npm run gen:api             # contracts/generated/openapi.json -> src/renderer/api/schema.d.ts
npm run typecheck
npm run lint
npm test                    # vitest
npm run build               # out/main, out/preload, out/renderer (relative asset URLs)
npm run mock-server         # http://127.0.0.1:8790, token "mock-token"
npm run e2e                 # Playwright: runs `build` first (pree2e), then drives out/; starts the mock server itself
npm run dev                 # the whole system: container + Vite + Electron (see "Dev loop")
npm run dev:web             # the same without Electron: http://127.0.0.1:5173/
npm run dev:down            # stop and remove this project's dev container
```

If `node_modules/electron/dist` is missing after `npm install` (postinstall skipped), run
`node node_modules/electron/install.js`.

## Dev loop

`pnpm run dev` is the development entry point too: it runs the same script as `npm run dev`
below. Run it from this `desktop/` directory; no separate frontend or renderer command is needed.
The run-page 3-D panes are this app's own WebGL2 renderer (`src/renderer/scene/`) and need nothing
installed. Full 3-D *viewing* is the separate **Tetravox** desktop app on your host: the Viewer page
writes a `*.tetravox.json` scene and hands it to that app (Settings ▸ Viewer shows where it was
found, or links to the download).

One command brings up the whole system — the container for your project, Vite with HMR, and
Electron already connected to that container. There is no token to read, paste or export.

```bash
cp .env.dev.example .env.dev     # then set TIT_DEV_PROJECT_DIR to your BIDS project
npm run dev                      # container + Vite + Electron
npm run dev:web                  # the same without Electron; open http://127.0.0.1:5173/
npm run dev:down                 # stop and remove this project's container
```

`.env.dev` is git-ignored and holds four settings, documented in `.env.dev.example`:
`TIT_DEV_PROJECT_DIR` (required), `TIT_DEV_IMAGE_TAG` (default `dev`), `TIT_DEV_PORT` (default
`8765`) and `TIT_DEV_MOUNT_REPO` (default `1`). Any of them can be overridden for one run from the
shell — the shell wins over the file — e.g. `TIT_DEV_PORT=8766 npm run dev`.

**What `npm run dev` does** (`scripts/dev.ts`):

1. **Container: attach, recreate or start.** Through the *same* `StackManager` the packaged app
   uses (`src/main/stack.ts`, driven by the Engine API from the root `docker-compose.yml`), so the
   container you develop against is the container the product creates — labels, mounts, health wait
   and all. It attaches to a running one when its recorded state already matches; recreates it, with
   a printed one-line reason, when it does not ("it mounts (none) at /ti-toolbox, this run wants
   …"); starts one when there is none.
2. **Recovers the token from the container** (`TIT_SERVER_TOKEN` in its own environment) or
   generates one into a container it starts. The token is never written to disk and never printed.
3. **Starts Vite** with `TIT_DEV_SERVER_URL` / `TIT_DEV_SERVER_TOKEN` in the environment, and
   **Electron**, which sees those two variables in an unpackaged run and connects immediately —
   the launcher form is never shown.

`Ctrl-C` stops Vite and Electron and leaves the container running, so the next `npm run dev`
attaches in well under a second. `npm run dev:down` is what stops the container.

A recreate stops the container and mints a **new** bearer token, so `npm run dev` refuses to
recreate one that has jobs in flight and names them: wait, `npm run dev:down` deliberately, or
`npm run dev -- --force`. Attaching never touches a running job.

**Live Python.** With `TIT_DEV_MOUNT_REPO=1` (the default) the worktree is bind-mounted at
`/ti-toolbox` with `PYTHONPATH=/ti-toolbox`, so every job runner (`simnibs_python -m tit.<module>`)
imports the working tree — an edit under `tit/sim`, `tit/opt`, `tit/analyzer`… is live for the next
job with nothing to restart. The same flag sets `TIT_SERVER_RELOAD=1`, which makes the image
entrypoint run the server as `uvicorn --reload --reload-dir /ti-toolbox/tit`, so an edit under
`tit/server/**` or `tit/jobs/**` restarts the server on its own. The watch is scoped to `tit/`
deliberately: uvicorn's default watch root is the working directory, which here is the whole
mounted repository — 5 834 directories, 2 815 of them `desktop/node_modules`, against 54 under
`tit/`. Set `TIT_DEV_MOUNT_REPO=0` to run the image's own baked-in `tit` instead, which is what a
user gets and therefore what to use when testing the image rather than the code.

**No token in your hands, and no `TIT_DEV_ORIGINS`.** The Vite proxy (`scripts/devProxy.ts`) stamps
`Authorization: Bearer <token>` and rewrites `Origin` to the server's own origin on every proxied
`/api`, `/auth` and `/ws` request — on `proxyReq` *and* `proxyReqWs`, since only the second fires
for the `/ws/system` upgrade. `tit/server/auth.py` treats a matching bearer as sufficient outright,
so the browser needs no cookie and no `?token=`, mutating requests pass the CSRF check without the
server having to allowlist Vite's origin, and a `docker restart` does not log the tab out (measured:
`GET /api/version` through the proxy answers 200 before and after a restart, with an empty cookie
jar). What this replaces: reading the token out of `docker inspect`, opening
`/auth/session?token=…` in the browser to mint a cookie, and starting the server with
`--dev-origin http://127.0.0.1:5173` / `TIT_DEV_ORIGINS=…` so that cookie would be accepted.

`npm run dev:web` does *not* use `electron-vite dev --rendererOnly`: measured against electron-vite
5.0.0, that flag only skips *rebuilding* main and preload and still calls `startElectron()`
afterwards, i.e. it opens a window. `scripts/devWeb.ts` instead resolves the same
`electron.vite.config.ts` through electron-vite's own exported `resolveConfig` and serves only its
`renderer` config with Vite — no second copy of the renderer configuration, and no Electron.

Browser mode against the mock server instead of a container: `npm run build && npm run mock-server`,
then open `http://127.0.0.1:8790/?token=mock-token`. Electron-only controls are hidden when
`window.tit` is undefined.

## E2E against a real server

```bash
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> npm run e2e
```

Screenshots land in `tests/e2e/artifacts/` (git-ignored).

## Security settings

Historical rationale: [original plan §2.8](../docs/dev/DECISIONS.md#retired-root-plan--2026-09-09).

`contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, `webSecurity: true`;
`will-navigate`/`will-redirect` allow only `app://launcher` and the connected server origin;
`setWindowOpenHandler` denies everything (http/https/mailto go to `shell.openExternal`);
`tit.connect({url, token})` is accepted only from the launcher page; the settings file stores the
last server URL, never the token. Main-process log: `app.getPath("logs")/main.log`.

The dev auto-connect (`TIT_DEV_SERVER_URL` + `TIT_DEV_SERVER_TOKEN` → `connect()` on ready, no
launcher) is guarded on `!app.isPackaged`: a packaged app must never be steerable into an arbitrary
server by an environment variable a user's shell happens to carry.

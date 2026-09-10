---
layout: wiki
title: Development & Testing
permalink: /wiki/development/
---

# Development & testing (v3)

Use a v3 source checkout with Docker running and Node.js 22.12 or newer. The repository's
`CONTRIBUTING.md` owns the full environment setup; `docs/dev/TESTING.md` owns the detailed
test strategy and release gate. This page is a quick entry point for trying and checking the app.

## Try the desktop without packaging

From the checkout:

```bash
cd desktop
npm install
npm run dev
```

This builds and opens the same welcome Overview used by the desktop app, with the complete
sidebar visible. Select a project by typing its directory or using **Browse…**. Docker starts
only when you open the project; an existing TI-Toolbox session requires an explicit attach or
recreate choice. **Switch project** selects another dataset in the same app. Closing Electron
stops/removes its container and exits. Rerun `npm run dev` after source changes to rebuild the
app. `npm run dev:launcher` is a compatibility alias for the same command.

For frontend hot reload in a browser, run `npm run dev:web` from `desktop/`. It starts the
development stack and Vite. Closing the browser or stopping Vite leaves Docker running;
`npm run dev:down` stops/removes that development stack. The developer CLI wrappers are
another browser entry point; see [the loader reference]({{ site.baseurl }}/installation/bash-cli/).

## Choose checks that prove the change

| Check | What it covers |
|---|---|
| Desktop types, lint and unit tests | UI logic, types and code conventions |
| Host Python tests | Server, jobs, configuration and path logic with heavy scientific libraries mocked |
| Container numerical tests | Numerical behavior against real libraries |
| Hidden Electron tests | Actual UI interactions against controlled mock services |
| Real workflow and packaged acceptance | Scientific outputs and the distributed app/image pairing |

From the repository root, after installing the contributor Python environment:

```bash
.venv/bin/python -m pytest tests/ -q
python3 dev/route_import_guard.py
python3 dev/contracts_check.py
```

From `desktop/`:

```bash
npm run typecheck
npm run lint
npx vitest run
```

For real numerical checks, use an existing development/test container with the checkout
mounted at `/ti-toolbox` (replace `<container>` with its actual name):

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

Host pytest success does not establish scientific correctness: it mocks SimNIBS and several
other libraries. Numerical test success also does not substitute for a completed end-to-end
simulation on representative data.

## Hidden UI tests and final build

Coordinate exclusive use of `/tmp/tit-e2e.lock` before running Playwright: tests share a mock
server and build output. From `desktop/`, run `TIT_E2E_OFFSCREEN=1 npm run e2e:quiet` under that
lock. The detailed testing guide in the checkout describes real-server credentials, scene
hooks and quiet-monitor limitations. An inconclusive visibility monitor is not a pass.

After tests, run `npm run build` from `desktop/` to restore the normal UI bundle. Release
acceptance additionally checks the actual packaged executable and matching scientific image;
a source build alone does not validate a release artifact.

## Legacy development

The [v2 development archive]({{ site.baseurl }}/wiki/v2-development/) retains the old Qt and
CircleCI instructions. They describe legacy v2 installations and do not apply to the v3 stack.

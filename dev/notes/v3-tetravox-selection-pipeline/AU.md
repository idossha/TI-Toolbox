# Lane AU — automatic Tetravox embed updates (A2–A5)

Plan of record: `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-A. Builds on lane U's
dynamic delivery (`dev/notes/v3-embed-convergence/u-notes.md`), which already had the install
root, the pin, the digest-verified installer and the protocol range. This lane adds the three
things that were missing: **an index that exists**, **a policy that acts on it**, and **an image
build that follows the same rule**.

## 0. The maintainer's question, answered before the file list

> *"shouldn't we just have our own installation of TetraVox within the container … update the
> Dockerfile and cut a new image and have a dynamic surface within the TI toolbox to accept the
> Tetravox instance whatever it might be … all the code and the logic on the TetraVox side?"*

**The dynamic surface already exists and is exactly what you describe** — and this lane did not
weaken it. TI-Toolbox names no Tetravox version anywhere: it pins a protocol **range** plus named
features (`tit/tetravox/protocol.py`, 20 lines), and a pane asks `embedCan(embed, "markers")`,
never `version >= x`. The image keeps baking a floor at `/opt/tetravox/embed`, and A5 makes that
bake resolve the newest compatible release by itself. So "update the image and ship whatever
Tetravox is current" **is** the primary path, and it now needs no Dockerfile edit at all.

What is genuinely optional is the *second* delivery path this lane adds — installing a 5–6 MB
tarball into the writable user-config root at runtime — and the honest tradeoff is:

| | Image only (your proposal) | Image floor + runtime install (as built) |
|---|---|---|
| Cost of a Tetravox bugfix reaching a user | a 6.66 GB image pull, gated on a TI-Toolbox image tag | 5–6 MB, no restart |
| Who decides when | whoever cuts the image; users pinned to a tag never get it | the user (Settings), or the policy |
| Code on the TI side | ~0 extra | `tit/tetravox/` ≈ 1 400 lines, ~450 of them this lane |
| Air-gapped install | works | works (the floor is untouched) |
| Failure mode | stale viewer, silently | one line in Settings |

The image tag is produced by `dev/update_version.py` as part of a TI-Toolbox release, so "cut a
new image per Tetravox release" is in practice a TI-Toolbox release per Tetravox release — the
thing the original ask ("we do not need to release a new version every time Tetravox updates")
asked to remove. That is the whole argument for the runtime path, and it is the only one.

**If you want the image-only shape, the deletion is clean and small**: drop `tit/tetravox/updates.py`,
the lifespan task in `app.py`, `/ws/tetravox`, `POST /api/tetravox/policy` and the switch in the
Settings card; keep `protocol.py`, `store.py`, `install.py`, the routes and the card (they are
lane U's, already shipped, and are what makes the image's bundle swappable at all); keep A5's
`build.sh` resolver, which is the "the image ships whatever Tetravox is current" half of your
proposal and is independent of everything else here. Say the word and I will cut it; nothing else
in this lane depends on the auto-update existing. Note the middle option too: keep the check,
default `auto_update` **off** — the app then only ever *tells* you a new Tetravox exists, and
installing stays a click. That is a one-line default change (`updates.read_policy`).

## 1. Files

| File | What |
|---|---|
| `tit/tetravox/updates.py` (new, 560 lines) | A2 GitHub Releases API + flat-mirror override, ETag/age cache, A3 policy + one pass of it, A4 prune-to-two, release **provenance** |
| `tit/tetravox/install.py` | `api.github.com` on the allowlist; the never-existing `releases.json` index moved out (docstring now names the auto path) |
| `tit/tetravox/__init__.py` | re-exports the new surface |
| `tit/server/routes/tetravox.py` | `GET /api/tetravox/updates?refresh=`, new `POST /api/tetravox/policy`, `auto_update` in the state |
| `tit/server/schemas.py` | `TetravoxUpdateOutcome`; `auto_update` / `checked_at` / `from_cache` / `last_outcome` |
| `tit/server/ws.py` | `EventHub` + `/ws/tetravox`, one event `tetravox.updated` |
| `tit/server/app.py` | `lifespan` starting the non-blocking 24 h check; `/ws/tetravox` in the dump |
| `contracts/openapi.v1.yaml` (+ `.json` via `dev/build_contract.py`, `schema.d.ts` via `pnpm run gen:api`), `contracts/SCHEMA-CHANGES.md` | one path, one query param, one component, four properties, one WS path |
| `container/blueprint/build.sh` + `README.md` | A5: `resolve_tetravox_tgz()` (curl + python3 stdlib), `--no-tetravox`, "Which Tetravox gets baked" |
| `desktop/src/renderer/pages/settings/{TetravoxCard.tsx,api.ts}` | the switch, "Check now" (forced), last-checked, last-outcome callout |
| `desktop/src/renderer/app/useTetravoxUpdated.ts` (new) + `App.tsx` (2 lines) | the toast |
| `desktop/tests/mock-server/server.mjs` | policy + refresh/cache + `/ws/tetravox` + `POST /api/__mock/tetravox-updated` |
| `tests/test_tetravox_updates.py` (new, 23 tests), `tests/test_tetravox_routes.py` (+6), `tests/test_tetravox_install.py` (−2, moved), `desktop/tests/unit/{tetravox-card,tetravox-updated-event,settings-warm-cache}`, `desktop/tests/e2e/settings.spec.ts` (+2), `desktop/tests/mock-server/contract.test.ts` | |

`contracts/events.schema.json` is deliberately **unchanged**: it describes one line of a job's
`events.jsonl`, and adding an app-level type would make every job-event reader accept a type no
job can emit. That is why `tetravox.updated` got its own socket rather than a branch in
`/ws/jobs` or `/ws/system`, both of which have consumers that parse one shape.

## 2. The five decisions, each with the failure it prevents

| # | Decision | Failure prevented |
|---|---|---|
| AU1 | **The index is the GitHub Releases API**, and the protocol comes from the `.manifest.json` **asset**, not from the tarball. | Lane U's `releases.json` never existed (404 for its whole live run — u-notes §4). A file someone must remember to commit is an index that goes stale silently. Reading the manifest asset means "can we host it?" costs ~2 KB, not 6 MB. |
| AU2 | **"Newer" is measured against the newest bundle *this updater* installed from a release** (`released` provenance in the cache), never against whatever is active. | The dev container runs a hand-installed embed calling itself **0.4.0**, from a pre-release branch; the first real release is **0.3.12**. Comparing against the active bundle answers "up to date" *forever* on the one machine where this matters. Tested directly (`test_a_manually_installed_dev_bundle_does_not_block_a_lower_numbered_release`). |
| AU3 | **Protocol is checked before the download, not only by the installer.** | The installer already refuses an out-of-range bundle — but only after fetching it, and the user then reads *"Could not install: that bundle speaks protocol 99"* instead of A1's *"Update TI-Toolbox to use it."* Demonstrated: with the pre-check removed the test fails `'failed' == 'unsupported'`, and the tarball is downloaded for nothing. |
| AU4 | **Rendering Settings costs no GitHub request.** The route answers from the cache; `refresh=true` is the button; the background pass is what refills it. | 60 unauthenticated requests/hour/IP. A card that checked on mount would spend the budget on nothing and tell a remote host that this install exists, on every visit. |
| AU5 | **The check is a task with a 5 s head start, and every network call is in a threadpool.** | A blocking `urllib` call on the event loop stalls every request for up to 30 s. The head start also means a short-lived process (`TestClient`, `--dump-openapi`) opens no socket at all. |

Two smaller ones worth stating: **"off" stops the installing, not the knowing** (the card still
lists what was found, with an explicit Install), and **the toast is not a reload** — mounted panes
keep their iframe (the old bundle is still on disk and still served to them); a new mount gets the
new one.

## 3. Gates — commands and real output

| Gate | Command | Result |
|---|---|---|
| Python, full | `python3 -m pytest tests/ -q` | **3734 passed, 47 skipped, 21 deselected** in 68 s (was 3712 before this lane; +23 new, −1 net from the two moved) |
| Python, mine | `python3 -m pytest tests/test_tetravox_updates.py tests/test_tetravox_routes.py -q` | 44 passed |
| Same, **in the container** (py 3.11.14, `simnibs_python`) | `docker exec ti-toolbox-fad740e5-tit-1 sh -lc 'cd /ti-toolbox && simnibs_python -m pytest tests/test_tetravox_updates.py -q'` | **21 passed in 10.04 s** |
| Import guard | `simnibs_python dev/route_import_guard.py` (in the container) | `route_import_guard: 21 route module(s) clean` |
| black | `python3 -m black --check` on the 12 files this lane touched | clean |
| Contracts | `python3 dev/build_contract.py`; `pnpm run gen:api` | both regenerated |
| Desktop typecheck / lint | `npx tsc --noEmit`; `npx eslint src/renderer tests` | clean / **0 errors**, 3 pre-existing warnings (`ui/VirtualList.tsx`) |
| Desktop unit | `npx vitest run` | 931 passed, 2 failed — **both other lanes'**: `contract.test.ts` misses 8 `/api/pipelines/*` operations lane PC declared but does not yet serve (my `POST /api/tetravox/policy` and `GET /ws/tetravox` are exercised and pass), and it was `settings-warm-cache` until I added the `setTetravoxPolicy` mock it needs — now green |
| e2e (mock, offscreen) | `npx playwright test tests/e2e/settings.spec.ts` | **4 passed (22–25 s)**, including the two new ones |
| e2e quiet check | `bash scripts/e2e-quiet-check.sh npx playwright test tests/e2e/settings.spec.ts` | `no new Electron/Chromium window reached the screen`; focus **unchanged** (Electron before = Electron after) — the script still prints FAIL because another lane's `npm run dev` window was already frontmost when the run started, which is exactly the pre-existing-window case it ignores for windows but not for focus |

### The live container, against the real GitHub API

`ti-toolbox-fad740e5-tit-1`, worktree mounted at `/ti-toolbox`, `--reload`:

```
GET /api/tetravox        → auto_update: true,
                           index_url: https://api.github.com/repos/idossha/tetravox/releases,
                           install_root: /root/.config/ti-toolbox/tetravox/embed
                           active 0.4.0 protocol 2, "pinned to installed 0.4.0"
GET /api/tetravox/updates → {"available": true, "releases": [],
  "message": "v0.3.11 carries no tetravox-embed-<version>.tgz asset;
              v0.3.10 carries no tetravox-embed-<version>.tgz asset;
              v0.3.9 carries no tetravox-embed-<version>.tgz asset",
  "from_cache": true, "checked_at": 1788664614.2,
  "last_outcome": {"action": "current", "message": "<the same sentence>", "at": 1788665504.4}}
```

That is the honest answer the plan predicted: 0.3.11 exists and carries no embed asset. The
`last_outcome` is the proof the **startup task ran on its own** — nothing in this session called
the policy; its timestamp lands ~5 s after each `--reload`. `?refresh=true` flips `from_cache` to
false and re-asks the API.

**Health is not delayed** (measured on the container, straight after a reload, while the check
was in flight):

```
200 0.040618   200 0.009273   200 0.009369   200 0.008551
200 0.008983   200 0.009230   200 0.008306   200 0.008516
```

worst 40.6 ms (first request, cold), then ~9 ms. The unit test
(`test_the_startup_check_does_not_delay_health`) asserts the same property against a 5 s-hanging
index, and its comment is explicit that `TestClient`'s blocking portal makes it a weaker guard
than this container measurement — moving the call off the threadpool did *not* make it fail.

### `build.sh` (A5), both directions

```
$ resolve_tetravox_tgz                       # against the real API, today
exit=1  → "no compatible Tetravox embed release found …; baking the placeholder."
$ resolve_tetravox_tgz                       # against a payload that carries the assets
https://github.com/idossha/tetravox/releases/download/v0.3.12/tetravox-embed-0.3.12.tgz
```
The second run also skipped a `prerelease: true` entry numbered 9.9.9 and read `protocol: 2` from
the manifest asset. The supported range is grepped out of `tit/tetravox/protocol.py`, not copied
into the script.

### Tests that had to fail first (each demonstrated, not asserted)

| Test | Code removed | Observed |
|---|---|---|
| `…protocol_past_the_supported_range_is_reported_and_never_installed` | the `protocol_supported` pre-check | `assert 'failed' == 'unsupported'` — and the 6 MB tarball was fetched before the installer refused it |
| `…dev_bundle_does_not_block_a_lower_numbered_release` | provenance baseline → newest installed | `assert 'current' == 'installed'`, message *"Tetravox 0.4.0 is the newest release"* — the exact TX caveat |
| `…digest_that_does_not_match_replaces_nothing` | (installer's check, lane U's) | still green through the automatic path: `outcome.action == "failed"`, `list_installed == []`, no pin |

## 4. Compatibility matrix

| TI-Toolbox | Supported embed protocol | Tetravox versions that satisfy it | What happens |
|---|---|---|---|
| this build (3.0.0-dev) | **1–2** (`tit/tetravox/protocol.py`) | 0.3.4 (protocol 1, the baked floor), 0.4.0-dev (protocol 2, the container's hand install), **0.3.12+** once TX's release job ships (protocol 2) | installed automatically when `auto_update` is on |
| this build | 3+ | any future Tetravox that bumps the protocol | listed, `compatible: false`, outcome `unsupported`: *"speaks embed protocol N, which this TI-Toolbox cannot host. Update TI-Toolbox to use it."* Never downloaded. |
| a future TI-Toolbox raising `SUPPORTED_PROTOCOL_MAX` to 3 | 1–3 | everything above, plus protocol 3 | one constant, in two files the cross-language test (`tests/test_tetravox_protocol.py`) keeps in step |

Named features per protocol are unchanged from E1: `volumes, meshes, cursor, probe, screenshot,
layers` at 1; `markers, pick, camera` at 2; a manifest's own `features` array always wins.

## 5. Open items

1. **No release carries an embed asset yet** — everything above is proved against the loopback
   fake GitHub (real assets, real digests, real manifests, in-container too) plus the real API's
   honest empty answer. The first end-to-end automatic install can only be run once TX's PR #35 is
   merged and 0.3.12 is tagged. The lookup expects exactly TX's names.
2. **`contract.test.ts` is red on lane PC's 8 `/api/pipelines/*` operations**, not on anything here.
3. **The rate-limit path is tested against a fake 403**, not a real one (I did not exhaust GitHub's
   budget from this IP on purpose).
4. **Unauthenticated only.** No token support: a token in a config file is a credential this app
   would then have to protect, for a public repo's public releases.

## 6. Proposed record entries (consolidation lane lands these)

**ARCHITECTURE.md** — append to the Tetravox/viewer section:

> The embed bundle has two delivery paths and one rule. The image bakes a floor
> (`/opt/tetravox/embed`), resolved at build time from the newest Tetravox release whose embed
> manifest's protocol is inside `tit/tetravox/protocol.py`'s range; the server may install a newer
> release into the user-config root at runtime, under the same rule. The rule — protocol range plus
> named features, never a version — is the only coupling between the two projects. A release past
> the range is reported, never installed.

**DECISIONS.md** — four entries:

- *The Tetravox release index is the GitHub Releases API.* A `releases.json` committed to the
  Tetravox repo was specified in E-series and never existed (404 for lane U's whole live run). The
  API is written by the release itself; the three assets (`.tgz`, `.tgz.sha256`, `.manifest.json`)
  make "can this build host it?" answerable for ~2 KB. `TIT_TETRAVOX_RELEASE_INDEX` keeps working
  for mirrors and accepts either shape. `api.github.com` joined the download allowlist.
- *Automatic updates are a policy (default on), stored beside the install root.* The server checks
  at startup and every 24 h and installs only a protocol-compatible release; off means check and
  report. The policy lives in `<install root>/policy.json`, not in the project's `settings.json`,
  because it is a property of the install root (a shared user-config mount), not of the project the
  server is bound to.
- *"Newer" is measured against release provenance, not against the active bundle.* A hand-installed
  or dev bundle can carry a version number ahead of every real release (the dev container's 0.4.0
  vs the first release 0.3.12) and would otherwise freeze the updater permanently.
- *App-level events get their own socket (`/ws/tetravox`), not a new type on `/ws/jobs` or
  `/ws/system`, and not an entry in `events.schema.json`.* Both existing sockets have consumers
  that parse exactly one shape, and `events.schema.json` describes a job's `events.jsonl`.

**ROADMAP.md** — one line under v3.0:

> Tetravox embed: automatic, protocol-gated updates (server-side check + policy + one toast);
> the image bake resolves the newest compatible release by itself. *Blocked on the first Tetravox
> release carrying embed assets (Tetravox PR #35).*

**desktop/DESIGN.md §Settings** — reword the Viewer engine card's rule 2:

> The card never reaches the network. It renders what the server's own background check found —
> when it last looked, what it decided, and what is installable — and "Check now" is the only
> control that asks the index again. Turning automatic updates off stops the installing, not the
> knowing.

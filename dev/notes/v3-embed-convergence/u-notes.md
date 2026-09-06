# Lane U — dynamic embed delivery (E1–E4)

Maintainer's brief: *"I would like a system where we do not need to release a new version every
time Tetravox updates; there should be some dynamic element that can update Tetravox internally."*

Plan of record: `dev/notes/v3-embed-convergence-plan.md` §1 (E1–E4) and §2 (lane U).
Everything below is measured in this worktree / the shared dev container
`ti-toolbox-fad740e5-tit-1` (http://127.0.0.1:8765, project `/Users/idohaber/datasets/000`).

## 0. Ground truth measured before writing anything (2026-09-04)

| Fact | Value | Consequence |
|---|---|---|
| Baked embed in the running image | `/opt/tetravox/embed`, `{"name":"@tetravox/embed","version":"0.3.4","protocol":1,"sha":"c56c3c84…"}` | The floor is real, not the Dockerfile's placeholder. |
| Baked layout | `index.html` + `assets/` + `manifest.json` **flat** in the served dir | An installer must reproduce *this* layout, not the tarball's. |
| Release tarball layout | `tetravox-embed-0.3.4/{manifest.json,dist/index.html,dist/assets/…,LICENSE,EMBED.md,*.schema.json}` | `dist/` + `manifest.json` is the served subset (`container/blueprint/Dockerfile.ti-toolbox` lines 299-321 does exactly this with `--strip-components=1`). |
| Writable root already mounted | host `/Users/idohaber/.config/ti-toolbox` → container `/root/.config/ti-toolbox` (rw) | E2's second root needs no compose change. |
| `PathManager.user_config_dir()` | staticmethod; prefers `/root/.config/ti-toolbox` when it exists, else `TIT_USER_CONFIG`, else platform config dir | The install root can be derived, not configured. |
| `tit/server/static.py` reads `settings.tetravox_embed_dir` **per request** | already re-checks `os.path.isdir` every time | A dynamic resolver needs no restart to take effect. |
| Contract gate is real | `desktop/tests/mock-server/contract.test.ts` asserts `exercised == declared` over every `openapi.v1.yaml` path+method | A new route costs: yaml + mock implementation + a `call()` line. Not optional. |

## 1. What was built, and the failure each decision prevents

| # | Decision | Failure it prevents | Where |
|---|---|---|---|
| U1 | **One table, two languages.** The supported protocol range and the named feature map live in `tit/tetravox/protocol.py` and `desktop/src/renderer/viewer/embedProtocol.ts`, and `tests/test_tetravox_protocol.py` reads *both files off disk* and fails if they disagree. | A renderer that thinks `markers` arrives at protocol 3 silently hides a control that works. Nothing else in the build catches that. |
| U2 | **A pane asks for a name, never a number.** `embedCan(caps.tetravox_embed, "markers")`. The server publishes the resolved `features` list; the renderer falls back to its own protocol map when the server is older. | The coupling the maintainer asked to remove — every new feature otherwise means a version comparison written into a page, and a TI-Toolbox release per Tetravox release. |
| U3 | **The manifest's own `features` array wins when it has one.** `features_for(protocol, declared)` returns it verbatim. | A future Tetravox release naming a feature this build has never heard of would otherwise need a TI-Toolbox change to be usable — which is exactly what E1 forbids. |
| U4 | **A pin (`active.json`), not "newest always wins".** Install writes the pin; `"baked"` is a legal pin value. | Rollback would otherwise be `DELETE`, which throws away the bundle you might want back — and re-installing to go forward is a download, not a click. |
| U5 | **Resolution happens per request** in `tit/server/static.py`, not at startup. Measured cost: **21.6 µs** with nothing installed, **95.1 µs** with three installed + a pin (2000 iterations, in the container). No cache. | A restart to pick up a viewer you just installed defeats the point of installing at runtime. And a cache would be state to invalidate for ~0.1 ms of saving on a request that then streams an 848 KB wasm chunk. |
| U6 | **`tetravox_embed_dir` keeps its meaning (the floor); a new `tetravox_embed_override` carries the dev override.** `--tetravox-dir` sets both. | "The operator pointed us at a directory" and "nobody said anything, so use the image's" are different facts; collapsing them means an installed bundle either can never win, or wrongly beats an explicit override. Every existing test that constructs `ServerSettings(tetravox_embed_dir=…)` still passes unchanged. |
| U7 | **Hand-rolled extraction, never `TarFile.extractall`.** | Measured, both interpreters: on the container's **Python 3.11.14** (`simnibs_python`), `extractall()` with no filter **writes `../escape.txt` outside the destination** — the host's 3.14 refuses it. A guard that only works on the developer's laptop is not a guard. |
| U8 | **certifi when the interpreter has no CA store.** | Measured live: `simnibs_python`'s OpenSSL default verify paths are the **conda build-time placeholders** (`/home/conda/feedstock_root/build_artifacts/openssl_split_…/ssl/cert.pem`), absent from the image, so *every* https request from the server failed `CERTIFICATE_VERIFY_FAILED` — including the only real-world install, from GitHub — while `curl` in the same container worked (its own bundle). §4 has the before/after. |
| U9 | **Loopback http is allowed; everything else must be https and on the allowlist, including every redirect hop.** | Without loopback nothing could be proved end to end at all. Without re-checking redirects, one open redirect on `github.com` would make the allowlist decoration. The digest is the integrity control either way. |
| U10 | **Settings shows the digest, checks only when asked, and states "no network" as a sentence.** | An install that hides what it verifies asks to be trusted rather than checked; a page that fetches an index on mount tells a remote host that this install exists on every visit; and an air-gapped install (E2's whole reason for keeping the baked floor) is a supported state, not an error to retry. |

### The code that makes E1 true

`tit/tetravox/protocol.py` — one range, one feature map, and the manifest's own list passed
through untouched:

```python
SUPPORTED_PROTOCOL_MIN = 1
SUPPORTED_PROTOCOL_MAX = 2
FEATURE_MIN_PROTOCOL = {"volumes": 1, …, "markers": 2, "pick": 2, "camera": 2}

def features_for(protocol, declared=None):
    if isinstance(declared, list):        # the embed's own manifest wins
        names = {i for i in declared if isinstance(i, str) and i}
        if names: return tuple(sorted(names))
    ...
```

So an **additive** Tetravox release requires no TI-Toolbox change at all: its protocol number is
already inside the range; `GET /api/capabilities` reports whatever features that protocol (or the
manifest) names; `embedCan(embed, "…")` answers from that list; and `POST /api/tetravox/install`
accepts it because `validate_manifest` checks the *range*, not a version. The only edit a
**breaking** release needs is `SUPPORTED_PROTOCOL_MAX` — in two files the cross-language test
keeps in step.

## 2. Files

| File | What |
|---|---|
| `tit/tetravox/protocol.py` | E1: supported range + feature map (new) |
| `tit/tetravox/store.py` | E2: two roots, the pin, per-request resolution, activate/remove (new) |
| `tit/tetravox/install.py` | E3: allowlist, digest-before-unpack, traversal-safe extraction, manifest validation, atomic activation, release index, TLS context (new) |
| `tit/tetravox/__init__.py` | re-exports (new) |
| `tit/server/routes/tetravox.py` | the five routes (new, no work at import time) |
| `tit/server/settings.py` | `tetravox_embed_override`, `tetravox_install_root`, their resolvers |
| `tit/server/__main__.py` | `--tetravox-install-root`; passes the two new fields |
| `tit/server/static.py` | `/tetravox/` serves the *resolved* bundle, per request |
| `tit/server/routes/capabilities.py` | `tetravox_embed` describes the **active** bundle + E1's fields |
| `tit/server/schemas.py` | `ProtocolRange`, `TetravoxRelease/State/Update/Updates`; `TetravoxEmbedCapability` extended |
| `contracts/openapi.v1.yaml` (+ `.json`, `desktop/src/renderer/api/schema.d.ts`) | additive: one tag, five paths, five schemas, four properties |
| `desktop/src/renderer/viewer/embedProtocol.ts` | E1's renderer half: `embedCan`, `embedShortfall`, `isSupportedProtocol` (new) |
| `desktop/src/renderer/pages/settings/TetravoxCard.tsx` | Settings → Viewer engine (new) |
| `desktop/src/renderer/pages/settings/{api.ts,index.tsx,PARITY.md}` | the five calls (+ `unwrapDetail`, which keeps the server's sentence), the card, the checklist |
| `desktop/tests/mock-server/server.mjs`, `desktop/tests/fixtures/capabilities.json` | an in-memory model of the same state machine |
| `tests/test_tetravox_{protocol,store,install,routes}.py` | 62 new host tests |
| `tests/conftest.py` | session-wide `TIT_TETRAVOX_INSTALL_ROOT` isolation (see §5) |
| `desktop/tests/unit/{embed-protocol,tetravox-card}.test.ts(x)`, `desktop/tests/unit/settings-warm-cache.test.tsx`, `desktop/tests/e2e/settings.spec.ts`, `desktop/tests/mock-server/contract.test.ts` | 17 new renderer tests + the contract coverage line |
| `docs/wiki/desktop-app.md`, `contracts/SCHEMA-CHANGES.md` | "Updating the viewer without updating the toolbox"; the additive-change entry |

## 3. The tests that had to fail first (each demonstrated, not asserted)

| Test | Code removed to make it fail | Observed |
|---|---|---|
| `test_a_tarball_whose_digest_does_not_match_is_rejected_and_nothing_is_written` | the `actual != expected` raise | `Failed: DID NOT RAISE InstallError` |
| `…hostile_archive_member…[_escaping_member / _absolute_member / _symlink_member]`, `…refuses_a_device_node` | `safe_extract`'s loop → `tar.extractall(dest_root)` | 4 failed. On the host's 3.14 the data filter raises `OutsideDestinationError`/`SpecialFileError` (wrong type, wrong message, no state guarantee); **in the container's 3.11.14 the escaping file is written outside the destination** — measured directly, see §4. |
| `test_a_protocol_outside_the_supported_range_is_refused_with_a_readable_message` | the range check in `validate_manifest` | `DID NOT RAISE` |
| the three hostile-member tests + `test_a_failure_part_way_through_never_becomes_the_active_bundle` | `finally: shutil.rmtree(staging…)` | `assert ['.staging-18894-1576616171087625'] == []` — the refusal left a half-extracted tree in the install root |
| `test_the_feature_map_matches_the_renderer` | `markers: 2` → `3` in the **TypeScript** file only | `assert {'markers': 3, …} == {'markers': 2, …}` |
| `tetravox-card.test.tsx` "does not touch the network until the user asks" + "shows each release with the digest…" | `enabled: checked` → `enabled: true`; the `<Digest>` row | 2 failed |

`test_activating_a_version_that_is_not_installed_is_a_readable_404` and the rollback tests are
covered by `store.activate` raising `StoreError` (`tests/test_tetravox_store.py`) and by the
route mapping it to 404 (`tests/test_tetravox_routes.py`), both green and both exercised live in §4.

## 4. The live loop, against `ti-toolbox-fad740e5-tit-1` (2026-09-04, every number measured)

The real tarball: `/Users/idohaber/00_development/tetravox-wt-embed/packages/embed/dist-pkg/tetravox-embed-0.3.4.tgz`,
`sha256 e09a401b0c05da6f8d577095b94ac96f6d6d822db5e9db4466c3b321a5a70003` (re-hashed inside the
container: identical). It was served over loopback http **from inside the container**
(`python3 -m http.server 8919 --bind 127.0.0.1` in `/tmp/tvx-lane-u`, started and killed by this
lane, nothing else touched) — a host-side server would need `host.docker.internal`, which is not
on the allowlist.

The baked and the installed bundle are the *same release* (0.3.4), so "which copy is being
served" is proved by the file identity in the HTTP response, not by the version string:

| Step | `/tetravox/manifest.json` `last-modified` / `etag` | `GET /api/tetravox` | `capabilities.tetravox_embed` |
|---|---|---|---|
| baseline | `Fri, 04 Sep 2026 02:35:28 GMT` / `"fc03092fca10e3e3a45e8fde8c85b99d"` | `0.3.4 baked /opt/tetravox/embed`, installed `[]`, reason *the version baked into the image* | `source: baked` |
| bad digest (`000…`) | unchanged | unchanged | — |
| host off the allowlist | unchanged | unchanged | — |
| **install** (0.14 s wall) | `Fri, 04 Sep 2026 18:33:38 GMT` / `"cf980b4a7ca4b885dfd28b551f5359b8"` | `0.3.4 installed /root/.config/ti-toolbox/tetravox/embed/0.3.4`, reason *pinned to installed 0.3.4* | `source: installed` |
| **roll back** (`activate {"version":"baked"}`) | `…02:35:28 GMT` / `"fc03092f…"` — byte-for-byte the baseline | `0.3.4 baked …`, **still installed `[('0.3.4', False)]`** | `source: baked` |
| forward again (`activate 0.3.4`) | `…18:33:38 GMT` | `installed /root/.config/…/0.3.4` | — |
| `DELETE /api/tetravox/0.3.4` | `…02:35:28 GMT` / `"fc03092f…"` | installed `[]`, back to the baked reason | `source: baked` |

Refusals, verbatim from the live server:

```
POST /api/tetravox/install {"sha256":"000…"}   → 400
  sha256 mismatch: the download is e09a401b…a70003, expected 0000…0000. Nothing was installed.
  (and /root/.config/ti-toolbox/tetravox did not exist afterwards — the root is not even created)
POST /api/tetravox/install {"url":"https://evil.example/x.tgz"} → 400
  evil.example is not an allowed download host. Allowed: github.com, objects.githubusercontent.com,
  release-assets.githubusercontent.com, raw.githubusercontent.com (extend with TIT_TETRAVOX_ALLOWED_HOSTS)
POST /api/tetravox/activate {"version":"9.9.9"} → 404   {"detail":"Not installed: 9.9.9"}
```

On disk after the install: `0.3.4/{index.html, manifest.json, assets/}` — **5.6 MB**, the same flat
layout the Dockerfile bakes — plus `active.json` = `{"version": "0.3.4"}`. The engine's wasm chunk
served from it: `/tetravox/assets/tvx_wasm_bg-B29ETMOe.wasm` → `200`, `content-type:
application/wasm`, `content-length: 848311`, `last-modified …18:33:38` (the installed copy's).

**TLS, before and after U8** — the finding this live run existed to catch:

```
before:  GET /api/tetravox/updates → {"available": false,
           "message": "Could not reach the release index (…): <urlopen error [SSL:
            CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer
            certificate (_ssl.c:1016)>"}
after:   GET /api/tetravox/updates → {"available": false,
           "message": "The release index answered 404 Not Found"}
```

i.e. the server now reaches `raw.githubusercontent.com` over verified TLS and reports the honest
answer: **there is no `packages/embed/releases.json` in the tetravox repo yet** (see §6, request
to lane T / the maintainer). Probe of the two interpreters in the container:

```
simnibs_python 3.11.14  openssl cafile /home/conda/feedstock_root/build_artifacts/openssl_split_…/ssl/cert.pem  → missing
                        certifi /root/SimNIBS-4.6/simnibs_env/lib/python3.11/site-packages/certifi/cacert.pem → present
                        default context FAIL / certifi context OK 200
/usr/bin/python3 3.10.12  default context OK 200, no certifi
```

**Left exactly as found**: the installed bundle removed through the API, then
`/root/.config/ti-toolbox/tetravox` (which only this lane had created) removed, the scratch http
server killed by an exact-match pattern, `/tmp/tvx-lane-u` and the four probe scripts deleted.
Final `capabilities.tetravox_embed`: `available true, version 0.3.4, protocol 1, source baked,
compatible true, supported {1,2}` — and `/tetravox/manifest.json` back to the baseline `etag`.

## 5. Two things that bit, worth not re-deriving

**A. `curl /api/health` right after a save does not prove the reload happened.** Measured here:
`tit/tetravox/install.py` was saved with the certifi fix, health answered `200` two seconds later —
and `GET /api/tetravox/updates` still returned the *old* module's TLS error. The worker had not
restarted yet; the 200 came from the pre-reload process. `touch tit/server/routes/tetravox.py`
plus a 4 s wait, and the same request returned the new answer. So the honest check after editing
`tit/**` on the shared container is: wait for the reload (~3-5 s here), then probe **something
that reflects the change**, not just `/api/health`. (This does not weaken §6/F1's rule — a broken
import still takes the server down — it means a green health check straight after a save is not
yet evidence that the new code imports.)

**B. `pkill -f 'http.server 8919'` kills its own shell.** `sh -lc 'pkill -f "http.server 8919"; rm -rf …'`
matched the shell's *own* command line, so the process died at the `pkill` and the cleanup after
it never ran. `pkill -f 'http[.]server 8919'` (a regex that does not match the literal bracketed
text in the shell's cmdline) is the fix. Anything cleaning up after itself in one `sh -lc` on this
container needs the bracket trick.

## 6. Requests to other lanes

1. **Lane M (or whoever owns `desktop/src/renderer/viewer/protocol.ts`): the envelope check must
   accept the range, not the constant.** `isEmbedMessage` today is
   `if (v["tvx"] !== PROTOCOL_VERSION) return false;` with `PROTOCOL_VERSION = 1`. If a
   protocol-2 embed stamps `tvx: 2`, every message from it is dropped and the viewer silently
   renders nothing — which would make E1's claim false at the one place it is easiest to miss.
   The one-line fix, using this lane's module (no new source of truth):
   ```ts
   import { isSupportedProtocol } from "./embedProtocol";
   // …in isEmbedMessage:
   if (!isSupportedProtocol(v["tvx"])) return false;
   ```
   I did not make it: `protocol.ts` is a verbatim copy of the upstream file and is lane M/T's to
   re-copy when protocol 2 lands. `embedProtocol.ts` (mine) is a separate file precisely so this
   is a one-line import for you.
2. **Lane T / the maintainer: publish `packages/embed/releases.json`.** "Check for updates"
   resolves `TIT_TETRAVOX_RELEASE_INDEX`, defaulting to
   `https://raw.githubusercontent.com/idossha/tetravox/main/packages/embed/releases.json`, which
   answers **404 today** (measured live in §4 — the request itself now works). The shape it
   expects, which `pack:embed` could emit next to the tarball:
   ```json
   {"releases": [{"version": "0.4.0", "protocol": 2,
                  "url": "https://github.com/idossha/tetravox/releases/download/embed-v0.4.0/tetravox-embed-0.4.0.tgz",
                  "sha256": "…64 hex…", "notes": "Protocol 2: points layer, pick, camera.",
                  "published": "2026-09-05"}]}
   ```
   Entries without a version, url or sha256 are dropped rather than shown; the tarball layout
   already produced by `pnpm --filter @tetravox/embed pack:embed` (`<name>-<ver>/manifest.json` +
   `<name>-<ver>/dist/`) installs as-is — that exact 0.3.4 tarball was installed live in §4.
3. **Lane M: the pane feature gate is `embedCan(caps.tetravox_embed, "markers" | "pick" | "camera")`**
   from `desktop/src/renderer/viewer/embedProtocol.ts`, and `embedShortfall(embed, feature)` is the
   single line to render when it answers false (E6's "the panes say so in one line"). Do not
   compare `protocol >= 2` in a page: the whole point is that the map moves in one place.
4. **Image (unowned): `container/blueprint/Dockerfile.ti-toolbox` could keep baking the floor
   unchanged** — nothing here needs it to change. If it ever *stops* baking one, `/tetravox/`
   returns 404 until something is installed, and `capabilities.tetravox_embed.available` is false,
   which the UI already renders.

## 7. Gates (all run in this worktree, 2026-09-04)

| Gate | Result |
|---|---|
| host `python3 -m pytest -q` | **3587 passed, 32 skipped, 21 deselected** in 49.2 s (baseline this morning 3519; +68 = `test_tetravox_{protocol 4, store 15, install 32, routes 17}`) |
| `python3 -m black` on every file this lane touched | clean (7 reformatted by me, then clean) |
| `python3 dev/contracts_check.py contracts/openapi.v1.json <dump>` | 187 problems, exit 1 — **identical to the count with this lane's paths/properties stripped out of the contract** (measured both ways); `grep -i tetravox` on the output: **0 hits** |
| `desktop`: `npm run typecheck` | clean |
| `desktop`: `npm run lint` | **0 errors**, 3 pre-existing warnings (`ui/VirtualList.tsx`, `react-hooks/incompatible-library`) |
| `desktop`: `npx vitest run` | **955 passed / 78 files** (was 935 with 3 failing in `scene-framing.test.ts` at 13:32, from another lane's concurrent edit to `src/renderer/scene/camera.ts` at 13:31:04 — green again by 13:44 without any change of mine) |
| `desktop`: `npm run build` (plain) | clean; bundle grepped for `__scene`/`__scenePane`/`Design gallery`: **0 hits**. `out/` left as a plain production build at 13:45:34 |
| e2e (mock), offscreen | `settings.spec.ts` **2 passed (11.3 s)**, quiet-check **PASS**, no window reached the screen |
| e2e (real container), offscreen | `tests/e2e/real/tetravox.spec.ts` **2 passed (5.2 s)** against `http://127.0.0.1:8765`, quiet-check **PASS** |
| mock-server contract coverage | `contract.test.ts` drives all five new operations; `exercised == declared` still holds |
| live API loop | §4 — install / roll back / forward / remove with the real 0.3.4 tarball, plus three refusals |

## 8. Open issues (none blocking)

1. **`viewer/protocol.ts` still pins `tvx === 1`** — §6 request 1. Until that one line changes, a
   protocol-2 embed's messages would be dropped by the Viewer even though everything in this lane
   would happily install and serve it. This is the single remaining place where E1's claim is not
   yet true end to end, and it is one import away.
2. **No release index exists yet** (`…/packages/embed/releases.json` → 404). "Check for updates"
   is therefore honest but empty until §6 request 2 lands; install by `{url, sha256}` works today
   and is what §4 used.
3. **`dev/contracts_check.py` still exits 1** on 187 pre-existing problems (routes typed
   `-> dict[str, Any]` have no declared schema in the dump). Unchanged by this lane, measured both
   ways; not in this lane's gate list.
4. **The allowlist is a constant plus an env var.** If Tetravox releases ever move off GitHub, an
   operator must set `TIT_TETRAVOX_ALLOWED_HOSTS`; there is deliberately no way to add a host from
   the UI, because "the page that installs code can also widen where it may be fetched from" is
   the shape of the problem the allowlist exists for.
5. **`ssl_context()` prefers the system store when one exists**, so a container that later gains a
   real CA bundle silently stops using certifi — correct, but it means an operator's corporate CA
   is honoured only where the interpreter's own store is present.

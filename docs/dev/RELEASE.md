# Releasing TI-Toolbox v3

How a version number becomes a Docker image, four desktop installers and a GitHub Release. This is
the document of record for the release path; `.github/workflows/release-v3.yml` is its executable
form and `.github/workflows/README.md` only points here.

## What ships

A v3 release is **two artifacts that must agree**:

| Artifact | Where it comes from | Where it goes |
|---|---|---|
| `idossha/ti-toolbox:<ver>` | `container/blueprint/build.sh` — SimNIBS, `tit`, the web UI, and the Tetravox embed, all baked | Docker Hub, plus a moving `:latest` |
| `TI-Toolbox-<ver>.{dmg,exe,AppImage,deb}` + macOS `.zip` | `desktop/`, packaged by electron-builder | GitHub Release assets |

The desktop app is a shell: it starts the image, then loads the UI over http from the container
(`desktop/src/main/index.ts` `loadURL`). So the app is useless if the image tag it resolves does not
exist. **That is the single failure mode this whole procedure is built around.**

The tag is resolved from `desktop/docker/docker-compose.v3.yml`:
`image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-<ver>}`. In a packaged app nothing sets `TIT_IMAGE_TAG`,
so the `:-` default *is* the shipped tag. If it still says `dev`, or last release's number, a
correctly-signed v3.0.0 app pulls the wrong image. `dev/update/update_version.py` rewrites it and the
`plan` job refuses to build when it disagrees with the tag.

## The path, end to end

1. **Bump.** `python dev/update/update_version.py --version X.Y.Z --dry-run` first, read the list,
   then run it without `--dry-run`. It rewrites every version site (below) and writes the release
   pages under `docs/releases/`.
2. **Review and commit** on the release branch. `git diff` should show only version strings and the
   generated release pages.
3. **Tag** `vX.Y.Z` and push it. `release-v3.yml` takes over.
4. **`plan`** re-derives the version from the tag and hard-fails if `desktop/package.json`,
   `tit/__init__.py`, `version.py` or the compose default disagree. It also extracts the release
   notes from `docs/releases/vX.Y.Z.md`.
5. **`image`** builds `idossha/ti-toolbox:<ver>`, smokes it (build provenance, `tit.__version__`
   matches the release, the Tetravox embed is present), and pushes it plus `:latest`.
6. **`desktop-validate`** builds **unsigned** artifacts for macOS arm64 + x64, Windows x64 and Linux
   x64 with Node 22, runs `desktop/scripts/verify-package.mjs` against each, and uploads them as
   workflow artifacts. Nothing is published.
7. **`create-release`** creates the GitHub Release — only after validation is green.
8. **`desktop-publish`** rebuilds signed and notarised and uploads to that release, refusing to start
   on macOS if any signing secret is missing, and verifying `codesign`/`spctl`/`stapler` afterwards.
9. **Verify by hand**: download the DMG on an Apple Silicon Mac and on Intel, open it, and let it
   pull the image. Steps 4–8 cannot prove the app *works*, only that it is built and labelled right.
10. **Announce**: the docs site picks up `docs/releases/` on the next `deploy-docs.yml` run.

Everything before step 7 is reversible. Everything after it is not, which is the whole reason the
unsigned validation job exists.

## Dry-running it

`workflow_dispatch` on `release-v3.yml` with `dry_run: true` (the default) runs `plan`, `image`
(build and smoke, **no push**) and `desktop-validate`, then stops. The unsigned installers land as
workflow artifacts. This is the supported way to exercise the pipeline; it never creates a release,
never moves `:latest` and never signs anything.

## Every version site

`update_version.py` owns these. Adding a new place a version is written and not teaching the script
about it is how releases go wrong quietly, so the `plan` job independently re-checks the four that
are load-bearing (marked ✓).

| File | What it sets |
|---|---|
| `tit/__init__.py` ✓ | the Python package version, and what `build.sh` reads to tag the image |
| `version.py` ✓ | the version/build metadata table |
| `desktop/package.json` ✓ | what electron-builder stamps into the bundle, `app.getVersion()`, and every artifact file name |
| `desktop/docker/docker-compose.v3.yml` ✓ | the image tag a packaged app falls back to |
| `docker-compose.yml` | the v2 stack's image + `TI_TOOLBOX_VERSION` |
| `dev/loader/docker-compose.dev.yml` | the dev loader's image |
| `resources/dataset_descriptions/*.json` | the SimNIBS image recorded in generated BIDS datasets |
| `CITATION.cff` | citation version + release date |
| `docs/releases/*`, `docs/_layouts/releases.html` | the generated release pages and sidebar |

Two of these were broken before the v3 release work and are worth knowing about: the script pointed
at `dev/bash_dev/docker-compose.dev.yml`, a path that no longer exists (it printed "Skipped (not
found)" and nobody read it), and it did not know about `desktop/package.json` at all.

## What `verify-package.mjs` checks, and why each check exists

`node desktop/scripts/verify-package.mjs <app-path> [--expect-version X.Y.Z] [--expect-runtime]`

It reads the built app's `app.asar` header directly and needs no dependencies, so it also works on a
downloaded artifact. It checks:

- **version matches the tag**, and the app is not the legacy launcher. This is audit finding REL-01
  in test form.
- **the main entry is actually bundled** — a `main` field pointing at a file `files:` excluded
  produces an app that installs and then does nothing.
- **`docker/docker-compose.v3.yml` is bundled.** `src/main/stack.ts#resolveComposeFile` reads it from
  `app.getAppPath()` at every stack start. The pre-fix `electron-builder.yml` shipped only `out/**`
  and `package.json`, so every packaged build died on first launch with `compose-invalid`. Found by
  running this script against a scratch `--dir` build; no unit test or `npm run build` can see it.
- **nothing dev-only or deleted leaked in** — `tit/gui` (the deleted PyQt GUI), `tests/`,
  `playwright.config.ts`, `node_modules`, TypeScript sources. Their presence means something is
  packaging the repository root instead of `out/**`.
- **the staged runtime matches the platform.** The shipping app is Docker-backed, so by default it
  asserts there is *no* bundled Python runtime; `--expect-runtime` is for the parked native build.
- **`resources/renderer/index.html` exists** — the `--static-dir` a natively spawned `tit.server`
  would serve. It is deliberately outside the asar (a plain OS process cannot read one).
- **the platform executable exists** under the name electron-builder was asked for.

Locally: `cd desktop && npm run package:dir && npm run verify:package`.

## The Tetravox embed

`build.sh` bakes the Tetravox **embed** at `/opt/tetravox/embed` — the browser build `tit.server`
serves at `/tetravox/`. With no `--tetravox-tgz` it asks the GitHub Releases API for the newest
non-draft, non-prerelease `idossha/tetravox` release whose embed manifest declares a protocol inside
the range `tit/tetravox/protocol.py` supports, and reads the digest from the release's own
`.tgz.sha256` sidecar.

**That asset does not exist yet** — it arrives with Tetravox PR #35's release. Until then the
resolver finds nothing and `build.sh` **exits non-zero**. This is correct and must stay correct: the
baked embed is the offline floor the runtime falls back to, and an image that ships a placeholder
viewer is worse than an image that was never built, because it fails at the user rather than in CI.

To release before that: pass `tetravox_tgz` + `tetravox_sha256` to the workflow dispatch, pinning an
exact tarball URL and its digest (the image verifies the digest before unpacking, which is why the
sha is required rather than optional).

## Signing and notarisation

macOS artifacts are signed with a Developer ID and notarised. The workflow supplies `CSC_LINK`,
`CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` and `APPLE_TEAM_ID` from repository
secrets, and the publish job's first step **fails closed** if any is empty — without it,
electron-builder cheerfully produces an unsigned artifact and publishes it, which is the worst
outcome because it looks like a success.

`electron-builder.yml` deliberately no longer contains `mac.identity: null`. That was a hard "never
sign" the workflow could not lift; unsigned builds are now produced by exporting
`CSC_IDENTITY_AUTO_DISCOVERY=false` (which the validation job and the `package`/`package:dir` npm
scripts do, so a developer's own certificate in the login keychain is never used by accident).

**The Developer ID certificate expires 2027-02-01.** A release after that date fails at the
secrets check or at signing until the certificate is renewed and `CSC_LINK` replaced.

Windows artifacts are **not** signed; users see a SmartScreen warning. Linux artifacts are unsigned
by convention.

## What only a real run can prove

Honest list of what has *not* been executed:

- The workflow has never run. It passes `actionlint` and every job's shell was written against the
  real scripts, but runner images, secret names and Docker Hub credentials are unverified.
- The image job's runtime. `build.sh` has one recipe and installs SimNIBS from scratch — 30–60+
  minutes on a native x86_64 runner, which is exactly why `.circleci/config.yml`'s
  `build-and-smoke-image` is documented as expected to time out. The 180-minute timeout here is a
  guess. If it proves to be the release's long pole the fix is a larger runner or a published base
  image, not a shorter timeout.
- macOS x64 packaging and Windows/Linux packaging were not run; only macOS arm64 `--dir` was built
  and verified locally. The config for the other targets is declared and lints, nothing more.
- Signing, notarisation and the `codesign`/`spctl`/`stapler` verification: never exercised on this
  branch.
- The Tetravox resolver has never successfully resolved a release, because no release carries the
  embed asset yet.

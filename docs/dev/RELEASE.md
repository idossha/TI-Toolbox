# Releasing TI-Toolbox v3, and what is still open

Two jobs, and they belong together: **§A** is how a version number becomes an image, four installers
and a GitHub Release; **§B** is the honest list of what is not done, which is what a release has to
be decided against. Gate *results* are in [`BENCHMARKS.md`](BENCHMARKS.md); the narrative is
[`HISTORY.md`](HISTORY.md).

---

# A. How we release

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

The tag is resolved from the root `docker-compose.yml`:
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
| `docker-compose.yml` ✓ | the image tag a packaged app falls back to — the one run spec, at the repository root |
| `resources/dataset_descriptions/*.json` | the SimNIBS image recorded in generated BIDS datasets |
| `CITATION.cff` | citation version + release date |
| `docs/releases/*`, `docs/_layouts/releases.html` | the generated release pages and sidebar |

Two of these were broken before the v3 release work and are worth knowing about: the script pointed
at `dev/bash_dev/docker-compose.dev.yml`, a path that no longer exists (it printed "Skipped (not
found)" and nobody read it), and it did not know about `desktop/package.json` at all. Both v2
compose entries are gone now: there is one compose file, at the root, and
`dev/loader/docker-compose.dev.yml` carries dev overrides only and names no image.

## What `verify-package.mjs` checks, and why each check exists

`node desktop/scripts/verify-package.mjs <app-path> [--expect-version X.Y.Z] [--expect-runtime]`

It reads the built app's `app.asar` header directly and needs no dependencies, so it also works on a
downloaded artifact. It checks:

- **version matches the tag**, and the app is not the legacy launcher. This is audit finding REL-01
  in test form.
- **the main entry is actually bundled** — a `main` field pointing at a file `files:` excluded
  produces an app that installs and then does nothing.
- **the run spec is bundled.** `src/main/stack.ts#resolveComposeFile` reads a `docker-compose.yml`
  at every stack start. The pre-fix `electron-builder.yml` shipped only `out/**` and
  `package.json`, so every packaged build died on first launch with `compose-invalid`. It now ships
  as an `extraResources` entry copied from the repository root (`files:` globs cannot reach outside
  the app directory) and lands at `Resources/docker-compose.yml`, which the script checks for by
  content, not just existence. Found by running this script against a scratch `--dir` build; no unit
  test or `npm run build` can see it.
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

---

# B. What is still open

Everything here is known, none of it is a surprise, and each row says why it is not done. This is the
list a release decision reads.

## The release path itself

| Open | Why it is not done |
|---|---|
| **`release-v3.yml` has never run.** A `workflow_dispatch` dry run (`dry_run=true`, which stops after the unsigned validation job) is the cheapest thing that would prove the plan → image → desktop-validate half | Only CI can run it. Locally, only macOS arm64 was packaged and verified; signing and notarisation have never been exercised on this branch. |
| **CI builds the from-scratch image recipe.** `Dockerfile.ti-toolbox.layered` was deleted and `build.sh` has one recipe; `.circleci/config.yml`'s `build-and-smoke-image` passed `--layered`, which is now accepted and ignored | A from-scratch SimNIBS install is 30–60+ minutes natively and far longer emulated, well past what a default `machine` resource class should absorb on every push. Nothing here provisions a larger or self-hosted executor, and no nightly or release-gated variant of the job exists yet. |
| **The Tetravox embed asset does not exist yet.** `build.sh` resolves nothing and exits non-zero, which is correct — an image shipping a placeholder viewer fails at the user rather than in CI | It arrives with Tetravox PR #35 and the `v0.3.12` tag; merging and tagging are the maintainer's. Pass `tetravox_tgz` + `tetravox_sha256` to the workflow dispatch to release before then. |

## Known follow-ups in the product

| Follow-up | Why it is not done |
|---|---|
| **Job re-adoption does not survive a server restart.** The manager keeps a child pid in memory only, so a `--reload` leaves a finished job at `running`/`stalled` with `pid: None` and its dependants queued behind it for ever | `status.json` already persists the `pid`/`create_time` pair for exactly this. `POST /api/jobs/{id}/force` is today's escape hatch and lands the job in `lost`. **The single most user-visible open gap.** |
| **`tests/e2e/real/mex.spec.ts` is the one red in the real leg.** It is written against the pre-jobs-table Optimizer throughout — a page-level Method radiogroup, a global Run name, a page-level Subcortical radio, a leadfield strip | All four are the global sections ADR row 28 dissolved into the row, and `mex` is no longer a method at all: it is *derived* from eight electrodes / four pairs. Making it green is a rewrite the way `ex.spec.ts` now does it, and a wrong one would be worse than an honest red. |
| **The `cluster-permutation` real job fails on Dataset 000** — every voxel is excluded as degenerate, so nothing is testable. It now says so instead of raising a numpy "zero-size array" traceback | Whether a 2-vs-1 unpaired contrast on those three images *should* be degenerate everywhere is a data question, not a code one. Worth answering: a real spec that accepts a failed job proves less than it looks like it does. |
| **An idle electrode can be invisible.** Worst measured contrast against the now-opaque scalp is 2/255, median 35 | A design call for the maintainer. A thin contour on *every* marker — not only the ones carrying a channel colour — would keep colour as the whole state signal, because the contour would be constant. `DECISIONS.md` 2026-09-06 (CX5). |
| **Two renderers, and no decision to converge them.** The Viewer sub-page draws with the Tetravox embed; the run-page panes draw with this app's own WebGL2 renderer | Deliberate for now: the panes draw packaged reference anatomy and need picking and marker behaviour this project controls, while the Viewer draws the user's data and wants the whole engine. Convergence is a future question again, not a settled one. |
| **`mex` "force left/right symmetry" raises `ValueError`** for SimNIBS's own `<sid>_leadfield_<net>.hdf5` naming | `tit/opt/mex/mex.py:118-128` uses `removesuffix("_leadfield")`, a no-op when the net comes *after* it. `tit/opt/leadfield.py::list_leadfields` already has the right split. Verified still open 2026-09-07. |
| **Every real e2e run rewrites two tracked smoke payloads** with a fresh run-id namespace, so the worktree is dirty after a gate | Churn by design: Level A replays what the UI sent, and the run id must be unique per run. It still costs every lane a `git checkout` it has to know about. |
| **`FlexConfig.output_folder` is the run name** while ex/mEx write `run_name` | Two names for one user-facing idea, inherited from two config dataclasses. Unifying is a server-side change. |
| **One job group per kind on the Optimizer.** A Run whose rows mix a flex-family and an ex-family method is two `POST /api/jobs/groups` calls and two group ids, which the page states rather than hides | `/api/jobs/groups` takes one `kind`; making one Run one group needs either a mixed-kind group on the server or a client-side grouping that would lie about cancel. |
| **`contracts/` holds three files for one contract** — `openapi.v0.yaml`, `openapi.v1.json` and the generated `openapi.json` | Nothing is broken; `dev/contracts_check.py` is green over all of it. It is a shape a newcomer has to be told about rather than read. |
| **Ex-search's symmetric buckets have no control on the Optimizer page.** `ExConfig.symmetric_bucket` / `symmetry_pairing` / `symmetry_eeg_csv` arrived from `main` in the v2.5.0 merge (`230fa10a`); the mEx form exposes its equivalents, the two-pair Ex form does not, so requests send the server defaults | A form addition plus a mirror-map precondition the page would have to explain (the EEG net has to yield a mirror for every bucket entry, or the run fails with a zero-candidate error). Worth doing next to the mEx controls rather than alone. |
| **The analyzer's multi-sphere ROI union is Python-only.** `Analyzer.analyze_spheres` and `_run_group`'s `spheres` key came from `main` (`90cc6ba8`); `AnalyzerConfig` has no `spheres` field, so no v3 job can request one | A config field, a contract regeneration and an Analyzer-page target control. The single-sphere path is unaffected, and a script can call `analyze_spheres` directly today. |
| Notebook **import** (`POST /api/pipelines/import`, reading `metadata.ti_toolbox.pipeline`) | Closes the round trip export already encodes. Parsing hand-edited Python stays a non-goal. |
| `POST /api/jobs/{id}/retry` | The Jobs page's selection grammar can cancel and pin a selection but not retry it, because there is no endpoint. |
| A saved pipeline's node forms open at their defaults | The document stores each node's built config; no page has a config → form-state reader. |
| `ex`/`mex`/`leadfield`/`source`/`stats` pipeline nodes are edited as JSON | Their builders need values only the Optimizer page computes, or have no v3 form at all. The JSON is still validated server-side. |
| **The Simulator node on the pipeline canvas is not yet the Simulator's jobs table** | The table was being rewritten in the same worktree while the canvas lane ran; the node still fans out per subject × montage on the server. |
| **The Viewer's `overrides` / `extras` server plumbing has no client.** Kept: additive, contract-declared and covered by `tests/test_viewspec_overrides.py` | The Menu does not set per-layer appearance by design (§10.1), so nothing calls it. Deleting it is a five-line change and the test file says exactly what would be lost. |
| Shared `useTableColumns` and `roiLabel(value, opts)` helpers; a `rowAction` slot on `SelectionList`; `tags` on `JobStatus` | Each is a small refactor across files three lanes were editing at once, or a contract change no lane would make unilaterally. |
| **Notebooks:** a variable explorer; interactive plots; saving the pipeline canvas's export straight to a notebook | The explorer is a route and a pane (`%whos`-shaped). Interactive plots need a privileged scheme for output frames, the way SUNA's `suna-output:` works — a shell change, not a notebook change. The canvas export is one button: `POST /api/notebooks` already accepts a document. |
| **OpenSSF best practices**, and the two standing invitations to contributors — more unit and integration tests, and docs maintenance | Nothing has been assessed against the badge criteria yet; `code-ql-analysis.yml` and `python-security.yml` cover part of the static-analysis rows. |

## Not claimed

This is not a release certification. Full scientific workflow validation on every supported runtime
platform, packaging, signing and release delivery remain open. CI reproduces synthetic tests; local
GPU and real-data evidence is recorded in `BENCHMARKS.md` rather than implied by a mock-server pass.

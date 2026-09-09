# Building, distributing and releasing TI-Toolbox

This is the operating procedure and remaining-work list. [ARCHITECTURE.md](ARCHITECTURE.md) §10
owns the internal/public boundary; [BENCHMARKS.md](BENCHMARKS.md) owns measured gates. Continue the
existing product and pipeline rather than creating a version-specific procedure or task ledger.

## A. Build and distribution modes

A usable desktop build is a **matching image and installer**. The source loaders use the same
root `docker-compose.yml`; an installed Python wheel has the fallback in `tit/launch.py`.
The runtime/app version identifies the code; an internal image tag identifies the exact build.
Do not overwrite an internal image tag after sharing it.

The existing `.github/workflows/release-build.yml` has three explicit modes:

| Mode | Image | Desktop | Public announcement |
|---|---|---|---|
| `build` (default) | Build, inspect, export | Unsigned packages and package validation | None |
| `internal` | Same checks, then push immutable `internal-*` tag | Unsigned workflow artifacts | No GitHub Release; no Docker `latest` change |
| `release` | Stable version tag, then production promotion after verification | Draft assets; macOS signing/notarization and artifact inventory | Explicit stable tag only; publish after all legs pass |

Use `image_tag` to name a cohort, or omit it for `internal-<full source SHA>`. CI stages the
matching image default into the packaged compose file and checks it with `verify-package.mjs`.
An exported image can be transferred and loaded with `docker load`; unsigned installers alone
cannot start on a clean machine if their image is neither preloaded nor available in a registry.

The generic `release-build.yml` workflow is already registered on the default branch (verified
2026-09-08); after pushing a reviewed candidate, dispatch that ref. Reusing this existing workflow
avoids a separate registration/bootstrap workflow. CircleCI runs its existing source and desktop gates on ordinary changes; its expensive
from-scratch image leg is explicitly selected through `build_image` with a compatible Tetravox pin.
That distinction must remain visible in test evidence: source CI is not an image-build receipt.

### Runtime version preparation

```bash
python3 dev/update/update_version.py --development --version 3.0.0-dev.1 --dry-run
python3 dev/update/update_version.py --development --version 3.0.0-dev.1
```

Development mode updates the runtime package and desktop/lock version only. Public `version.py`,
citation metadata and release announcements stay unchanged. Stable version preparation is separate;
authored notes are preserved, and public-note generation requires explicit `--publish-notes` plus
`--notes-file`. See `dev/update/README.md`. Do not promote the public release just to build locally.

### Tetravox dependency

TI embeds the browser bundle, not the Tetravox desktop executable. Tetravox main currently lacks
that embed; PR #35 supplies protocol 3. Its published v0.4.0 release has no embed assets as inspected
on 2026-09-08. This is why a verified branch artifact is temporarily needed; it is not a permanent
fork requirement.

For local/internal builds, `container/blueprint/build.sh` accepts an exact tarball URL and SHA256:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:internal-20260908.1 \
  --tetravox-tgz "$TETRAVOX_TGZ" --tetravox-sha256 "$TETRAVOX_SHA256"
```

Serve only the artifact directory locally; Docker Desktop can reach it through
`host.docker.internal`. A hosted CI build needs a URL reachable from its runner. Without a pin,
the resolver requires compatible published embed assets and fails if none exist. The verified local
bundle is version 0.4.0 / protocol 3 from Tetravox commit `3dd3955be40d792aec07781cc89e23f3f1ed4f0f`,
SHA256 `0afbf2c5792cd32c02d4bb4e6672cc3c0b0234c321cebcea6ea155e723b98daf`.

### Optional FastSurfer checkpoint cache

The same `container/blueprint/build.sh` accepts a verified cache of the official FastSurfer
VINN v2.0.0 weights. Use it when downloading the checkpoints inside the build is unreliable;
it is not a different image recipe or permission to substitute unverified model weights.

```bash
container/blueprint/build.sh --tag "$INTERNAL_IMAGE_TAG" \
  --tetravox-tgz "$TETRAVOX_TGZ" --tetravox-sha256 "$TETRAVOX_SHA256" \
  --fastsurfer-checkpoints-tgz "$FASTSURFER_CACHE_URL" \
  --fastsurfer-checkpoints-sha256 "$FASTSURFER_CACHE_SHA256"
```

Both cache flags are required together: the URL must be HTTP(S), reachable from the Docker
build, and the SHA-256 must be 64 lowercase hexadecimal digits. The archive must contain
`aparc_vinn_axial_v2.0.0.pkl`, `aparc_vinn_coronal_v2.0.0.pkl` and
`aparc_vinn_sagittal_v2.0.0.pkl` at its root. The image recipe verifies the archive digest
before extracting those three named, nonempty files and retains `cache-archive.sha256` beside
the checkpoints. A local artifact server may be reached through `host.docker.internal`;
hosted runners need their own reachable URL. Do not treat an ephemeral local port as a
permanent artifact location.

Verify checkpoint sizes and checksums against the official FastSurfer distribution metadata
before making the archive, including when recovering cached files from an existing image.
A matching archive hash proves transport integrity, not that the weights came from the
intended upstream release. Keep the source image identity (if used), official metadata URL,
per-file upstream checksums and SHA-256 values, archive name and archive SHA-256 in
`dist/internal/fastsurfer-cache-provenance.json` with the build artifacts. The current cache
receipt lives there; it is not a new documentation roster or proof of a completed image.

Omit both flags to use FastSurfer's official checkpoint downloader with TLS verification.
Do not disable TLS verification to get a build past a certificate or network failure; use a
verified cache or fix the transport. Checkpoint verification does not validate the image's
other dependencies or its scientific outputs.

**Current real-image build: incomplete.** The NumPy/Blender dependency conflict has a verified
separate-runtime fix in a disposable container. The verified cache and accepted build arguments
do not establish a valid baked image; final build and real-image acceptance remain pending, with
executed evidence recorded in [BENCHMARKS.md](BENCHMARKS.md).

### Optional Blender download cache

`build.sh --blender-archive <http(s)-url>` changes only the transport for the pinned official
Blender 4.4.3 Linux archive. The recipe still requires SHA-256
`8d3be07d2bc412b502c6bfe3cfe3e22195a4164076867da987ce148d73c27946` before extraction.
Use this when a verified local cache is available and the upstream transfer fails. Omitting the
option uses the official mirror with TLS verification and bounded transfer retries.

### Local and colleague acceptance

Use a copy of a representative project. Verify a final image without a development source/UI mount,
then the Python and shell loaders, and the packaged app. The running version, image identity,
viewer manifest and actual job outputs must agree with the artifact receipt. Real e2e requires
`TIT_E2E_PROJECT_HOST` explicitly so cleanup cannot silently target the maintainer's dataset.

The internal cohort tests its actual platforms and workflows. Full macOS Intel/Apple Silicon,
Windows and Linux package validation remains a production requirement; one local Mac does not
prove the other platforms. User-facing setup and known limits are in
[Installation](../installation/installation.md#internal-colleague-testing).

### Public publication later

Only a separate production decision may publish the stable release or move Docker `latest`.
Public toolbox update checks read GitHub's latest published release; internal image publication
alone does not notify existing users. The current desktop has no automatic toolbox update wiring.
Tetravox's compatible-viewer update mechanism is independent.

Real publishing needs Docker Hub access and macOS `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`,
`APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`. Build-only rehearsal needs none of those secrets.
Presence of a secret name does not prove its value works. macOS signing, Gatekeeper, notarization
and first launch must be measured before claiming them; Windows artifacts are unsigned.

## B. Current readiness and follow-ups

Internal preparation is in progress. The cohort identity is `internal-20260908.1`, runtime
`3.0.0-dev.1`. Local image build, package verification, isolated real UI gates, hosted CI, registry
publication and merge evidence must be recorded in BENCHMARKS.md before closing those steps.
No public release or update announcement is authorized by this preparation.

Two previously listed blockers were stale: startup reconciliation deliberately interrupts old jobs
rather than leaving them running forever (`tit/jobs/manager.py`), and mEx uses the shared symmetry
map helper (`tit/opt/mex/mex.py`). The obsolete mEx UI test now uses row-based Ex with eight
electrodes; its real execution is a required integration check, not inferred from the edit.

### Product follow-ups retained from the existing roadmap

These are limitations or future extensions, not evidence that all internal workflows failed. Keep
the selected colleague workflows explicit and record failures against them. Older measurement claims
below remain tied to their original BENCHMARKS/decision entries rather than this preparation pass.

| Follow-up | Why it is not done |
|---|---|
| ~~**The `cluster-permutation` real job fails on Dataset 000** — every voxel is excluded as degenerate~~ **Closed 2026-09-07 (CX9).** It was a code bug, not a data question: [SCI-09](SCIENTIFIC-CORRECTIONS.md#sci-09) | The pooled variance was `(n-1) * np.var(x, ddof=1)`, which for the singleton group of a 2-vs-1 design is `0 * nan == nan`. Every voxel came back `nan` and was dropped. Fixed in `1b5ffdd7`; the contrast is now computed and matches `scipy`. **What remains true** is that three subjects admit only three relabellings, so no cluster can clear `p < 0.05` — a real spec on Dataset 000 should assert a *succeeded* job with **zero** significant clusters, which is a much stronger assertion than accepting a failure. |
| **An idle electrode can be invisible.** Worst measured contrast against the now-opaque scalp is 2/255, median 35 | A design call for the maintainer. A thin contour on *every* marker — not only the ones carrying a channel colour — would keep colour as the whole state signal, because the contour would be constant. `DECISIONS.md` 2026-09-06 (CX5). |
| **Two renderers, and no decision to converge them.** The Viewer sub-page draws with the Tetravox embed; the run-page panes draw with this app's own WebGL2 renderer | Deliberate for now: the panes draw packaged reference anatomy and need picking and marker behaviour this project controls, while the Viewer draws the user's data and wants the whole engine. Convergence is a future question again, not a settled one. |
| **Every real e2e run rewrites two tracked smoke payloads** with a fresh run-id namespace, so the worktree is dirty after a gate | Churn by design: Level A replays what the UI sent, and the run id must be unique per run. It still costs every lane a `git checkout` it has to know about. |
| **`FlexConfig.output_folder` is the run name** while ex/mEx write `run_name` | Two names for one user-facing idea, inherited from two config dataclasses. Unifying is a server-side change. |
| **One job group per kind on the Optimizer.** A Run whose rows mix a flex-family and an ex-family method is two `POST /api/jobs/groups` calls and two group ids, which the page states rather than hides | `/api/jobs/groups` takes one `kind`; making one Run one group needs either a mixed-kind group on the server or a client-side grouping that would lie about cancel. |
| **Ex-search's symmetric buckets have no control on the Optimizer page.** `ExConfig.symmetric_bucket` / `symmetry_pairing` / `symmetry_eeg_csv` arrived from `main` in the v2.5.0 merge (`230fa10a`); the mEx form exposes its equivalents, the two-pair Ex form does not, so requests send the server defaults | A form addition plus a mirror-map precondition the page would have to explain (the EEG net has to yield a mirror for every bucket entry, or the run fails with a zero-candidate error). Worth doing next to the mEx controls rather than alone. |
| **The analyzer's multi-sphere ROI union is Python-only.** `Analyzer.analyze_spheres` and `_run_group`'s `spheres` key came from `main` (`90cc6ba8`); `AnalyzerConfig` has no `spheres` field, so no v3 job can request one | A config field, a contract regeneration and an Analyzer-page target control. The single-sphere path is unaffected, and a script can call `analyze_spheres` directly today. |
| **A project seeded before 2026-09-07 keeps the broken worked example.** `examples/getting-started.ipynb` cell 3 called the pre-v2.5.0 `calc.get_TI_vectors(E1, E2)` and raised `ValueError: mTI requires an even number of fields >= 2, got 3`; `tit/server/notebooks.py` is fixed, but `seed_example()` writes the file only when it is absent | Deliberate: re-seeding would clobber a user's own edits to their copy, and the `.seeded` stamp exists precisely so a deleted example is not handed back. The user fix is to delete `code/ti-toolbox/notebooks/examples/getting-started.ipynb` and reopen Notebooks. A "your example is older than the shipped one" prompt is the real answer and is not built. |
| **A running job carries no ETA.** `JobStatus` has no remaining-time field, so the Jobs table and the detail pane can show elapsed time and a stage counter but never "about 6 minutes left" | The only ETA in the product is the *pre-flight* one on the Optimizer's leadfield strip (`tit/jobs/eta.py`, `planLeadfieldEta`), which is a plan for a job that has not started. Extending it to a running job means either a per-kind model on the server or a client-side extrapolation from `progress.pct`, and an extrapolation that is wrong for the FEM stages — where the last 10 % is most of the wall clock — would be worse than no number. The System page is CPU/memory over five minutes and says nothing about jobs. |
| **Tetravox PR #35 is at 0.4.0 / protocol 3 and is not released.** The dev image already carries that embed, and `Settings ▸ Viewer engine` installs from the GitHub Releases index of `idossha/tetravox` | Nothing in this repository can close it: the release is cut in the Tetravox repository. Until it is, the auto-update check finds no release carrying `tetravox-embed-0.4.0.tgz` and a user's app stays on the bundle its image shipped — which works, but means the "update the viewer without updating the toolbox" promise is untested end to end against a real index. For internal builds, the verified baked bundle is sufficient; public viewer update delivery remains unverified. |
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

An internal candidate is not production certification. Platform testing, signing and final scientific
acceptance remain explicit. A mock pass, a healthy server or an artifact file alone proves none of
the other legs. Record only executed commands and distinguish actual computation from start/cancel smoke.

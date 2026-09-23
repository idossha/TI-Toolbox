# Releasing TI-Toolbox

Versioning, packaging and publication procedure. [ROADMAP.md](ROADMAP.md) owns current
acceptance priorities; [TESTING.md](TESTING.md) owns validation. Workflow triggers and recovery
are documented in [AUTOMATION.md](AUTOMATION.md).

## Docker distribution tags

The application image is `idossha/ti-toolbox:v3.0.1`. Small v3.0.1 patches rebuild and
republish this same mutable tag; a new patch version gets a new tag and older tags are left alone. Record the source commit and image digest for each push;
the tag alone does not identify an exact build. Fresh launcher starts check for updates,
while attaching to a running session preserves its image and computations.

The optional worker is `idossha/ti-toolbox:freesurfer-20260910`, mirroring upstream
FreeSurfer 7.4.1. Keep this dated tag fixed; publish a new dated worker tag only when its
contents change and update `tit/pre/freesurfer.py` together. No persistent worker is needed.
Superseded internal application tags can be removed after verifying the replacement.


## A. Build and distribution modes

A usable desktop build is a **matching image and installer**. The source loaders use the same
root `docker-compose.yml`; an installed Python wheel has the fallback in `tit/launch.py`.
The runtime/app version identifies the release line; the source SHA and registry digest identify
the exact build published under its mutable Docker tag.

Docker build, smoke verification and push are **manual**, as in v2. The executable workflow has
only two modes: `build` produces verified unsigned workflow artifacts; `release` signs/notarizes
macOS installers, verifies all platforms, attaches them to a draft, adds `SHA256SUMS`, checks the
complete inventory and publishes. Neither mode builds, exports, loads or pushes Docker images,
and neither changes Docker `latest`. There are no Docker Hub secrets in the executable workflow.

Before publishing executables, build and validate the version image locally, then push explicitly:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:v3.0.1
# Complete the local release tests and no-source-mount image acceptance in TESTING.md first.
docker run --rm --entrypoint cat idossha/ti-toolbox:v3.0.1 /etc/ti-toolbox-build.json
docker run --rm --entrypoint simnibs_python idossha/ti-toolbox:v3.0.1 -c 'import tit; print(tit.__version__)'
docker push idossha/ti-toolbox:v3.0.1
docker manifest inspect --verbose idossha/ti-toolbox:v3.0.1
```

The pushed tag must be a plain single-platform `linux/amd64` manifest, not an OCI index: the
`docker manifest inspect --verbose` output above is one object with `"architecture": "amd64"`, not
a list. `build.sh` passes `--platform linux/amd64 --provenance=false --sbom=false` for this
(`tests/test_image_build_manifest.py` guards it). Root cause, 2026-09-23: the v3.0.0 re-release was
built by `build.sh` without those flags on Docker Desktop's containerd image store, where
`docker build` is BuildKit and attaches a provenance attestation by default; `docker push` then
published an index (amd64 plus an `unknown/unknown` attestation), and an unpinned pull on Apple
Silicon failed with "no matching manifest for linux/arm64/v8". A plain manifest only warns. The
desktop app, `loader.sh`, `tit/launch.py` and `docker-compose.yml` also pin `linux/amd64` on every
pull and create, so an index can no longer break a launch either way. The release workflow's
`image-available` job runs `verify_release_assets.py --image-manifest`, which refuses a tag that
resolves to an index or manifest list, so a mis-pushed image blocks publication.

Keep source SHA, clean/dirty provenance, tests and registry digest with the manual publication
receipt. The reusable mutable version-line tag policy above is unchanged. CI reads only registry
manifest metadata to require a published `linux/amd64` version image; it downloads no image layers
and does not claim to verify the image's runtime, scientific outputs or exact source SHA. The
manual image owner is responsible for the image/installer pairing and its acceptance.

### Recovering an existing immutable release tag

A failed release can use the repaired workflow on `main` without moving its tag:

```bash
gh workflow run release-build.yml --ref main -f mode=release -f release_tag=v3.0.0
```

The control workflow's guards run from the invoked revision; candidate version checks and notes
read a separate checkout of `refs/tags/v3.0.0`. Every executable checkout uses that tag's resolved
full SHA, and uploads name that release explicitly. The existing tag is never rewritten and newer
`main` product code is never substituted. Existing public releases are refused before asset
replacement; a failed draft can be resumed. Missing manifests, package/signature checks or required
assets leave the release unpublished. Publication requires all seven installer/archive assets and
`SHA256SUMS`. Verify the final distributed platforms separately; workflow green is not a real
first-launch result on every supported host.

CircleCI's daily source/desktop regression is separate; its optional `build_image` verification
remains an explicit development check and does not publish images.

### Runtime version preparation

Runtime and public metadata are aligned at `3.0.1`. For future development builds, use the
development updater below; it leaves the public update source unchanged. Run the stable updater
only when cutting the corresponding release.

```bash
python3 dev/update/update_version.py --development --version X.Y.Z-dev.N --dry-run
python3 dev/update/update_version.py --development --version X.Y.Z-dev.N
```

Development mode updates the runtime package and desktop/lock version only. Public `version.py`,
citation metadata and release announcements stay unchanged. Stable version preparation is separate;
authored notes are preserved, and public-note generation requires explicit `--publish-notes` plus
`--notes-file`. See `dev/update/README.md`. Do not promote the public release just to build locally.

### Loader-verified checksum manifest

`finalize` downloads every attached asset, writes `SHA256SUMS` over them and uploads it before the
draft is published; `dev/update/verify_release_assets.py` requires it in the inventory. `loader.sh`
and `tit/cli.py` refuse to install a desktop app whose SHA256 is not listed there
(docs/dev/DECISIONS.md, 2026-09-15), so a release without this asset leaves every loader run in
browser fallback.

### TetraVox dependency

The image no longer includes a browser viewer bundle. Desktop installs the pinned official native
release defined in `desktop/src/main/tetravoxNative.ts`, verifying the recorded SHA256 before
extraction. Changing that pin requires OS-specific installation and packaged render checks.
The native-only TetraVox source changes must be released upstream before selecting their new artifact;
a local source build is not an official downloadable release.

### Optional FastSurfer checkpoint cache

The same `container/blueprint/build.sh` accepts a verified cache of the official FastSurfer
VINN v2.0.0 weights. Use it when downloading the checkpoints inside the build is unreliable;
it is not a different image recipe or permission to substitute unverified model weights.

```bash
container/blueprint/build.sh --tag "$INTERNAL_IMAGE_TAG" \
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
[Installation](../wiki/installation.md#install-from-source).

### Local development testing

Use the [development loop](../../CONTRIBUTING.md#development-environment) for current-checkout
code and [docs preview](../README.md) for the local website. Source-mounted testing does not
replace acceptance of a rebuilt image with no source/UI mounts.

### Production promotion

Only a separate production decision may publish the stable release or move Docker `latest`.
Public toolbox update checks read GitHub's latest published release; internal image publication
alone does not notify existing users. The current desktop has no automatic toolbox update wiring.
Tetravox's compatible-viewer update mechanism is independent.

Manual image pushes need Docker Hub access on the operator's machine. Executable publication
needs macOS `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID` and `APPLE_APP_SPECIFIC_PASSWORD`.
The public Apple Developer team ID defaults to `3BMY24SA43` (the v2 release team); an existing
`APPLE_TEAM_ID` secret can override it. Build-only rehearsal needs none of those secrets.
Presence of a secret name does not prove its value works. macOS signing, Gatekeeper, notarization
and first launch must be measured before claiming them; Windows artifacts are unsigned.

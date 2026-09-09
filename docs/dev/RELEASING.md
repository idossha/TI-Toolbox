# Releasing TI-Toolbox

Versioning, packaging and publication procedure. [ROADMAP.md](ROADMAP.md) owns current
acceptance priorities; [TESTING.md](TESTING.md) owns validation. Workflow triggers and recovery
are documented in [AUTOMATION.md](AUTOMATION.md).

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

TI embeds the browser bundle, not the Tetravox desktop executable. At the 2026-09-08 dependency review, the required protocol-3
embed was supplied by Tetravox PR #35 rather than published v0.4.0 assets. Recheck upstream
availability before the next distribution build. This is why a verified branch artifact is temporarily needed; it is not a permanent
fork requirement.

For local/internal builds, `container/blueprint/build.sh` accepts an exact tarball URL and SHA256:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:internal-20260908.1 \
  --tetravox-tgz "$TETRAVOX_TGZ" --tetravox-sha256 "$TETRAVOX_SHA256"
```

Serve only the artifact directory locally; Docker Desktop can reach it through
`host.docker.internal`. A hosted CI build needs a URL reachable from its runner. Without a pin,
the resolver requires compatible published embed assets and fails if none exist. Record the bundle commit, version, protocol and digest with each build receipt.

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
[Installation](../installation/installation.md#install-from-source).

### Local development testing

Use the [development loop](../../CONTRIBUTING.md#development-environment) for current-checkout
code and [docs preview](../README.md) for the local website. Source-mounted testing does not
replace acceptance of a rebuilt image with no source/UI mounts.

### Production promotion

Only a separate production decision may publish the stable release or move Docker `latest`.
Public toolbox update checks read GitHub's latest published release; internal image publication
alone does not notify existing users. The current desktop has no automatic toolbox update wiring.
Tetravox's compatible-viewer update mechanism is independent.

Real publishing needs Docker Hub access and macOS `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`,
`APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`. Build-only rehearsal needs none of those secrets.
Presence of a secret name does not prove its value works. macOS signing, Gatekeeper, notarization
and first launch must be measured before claiming them; Windows artifacts are unsigned.


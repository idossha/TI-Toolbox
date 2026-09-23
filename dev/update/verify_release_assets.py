#!/usr/bin/env python3
"""Fail before public release promotion if a required artifact is absent or empty."""

import json
from pathlib import Path
import sys


def verify_assets(version: str, release: dict) -> None:
    if release.get("isDraft") is not True:
        raise ValueError("release must remain a draft until verification finishes")
    expected = {
        f"TI-Toolbox-{version}.dmg",
        f"TI-Toolbox-{version}-arm64.dmg",
        f"TI-Toolbox-{version}-mac.zip",
        f"TI-Toolbox-{version}-arm64-mac.zip",
        f"TI-Toolbox-{version}.exe",
        f"TI-Toolbox-{version}.AppImage",
        f"ti-toolbox_{version}_amd64.deb",
        # The manifest loader.sh and tit/cli.py check before installing the desktop app.
        "SHA256SUMS",
    }
    present = {
        asset["name"] for asset in release.get("assets", []) if asset.get("size", 0) > 0
    }
    missing = expected - present
    if missing:
        raise ValueError(
            f"missing or empty release assets: {', '.join(sorted(missing))}"
        )
    print(f"Verified {len(expected)} required nonempty release assets")


# A tag that resolves to an index (e.g. amd64 plus a BuildKit attestation) makes an unpinned pull
# on Apple Silicon fail with "no matching manifest for linux/arm64/v8" (RELEASING.md, 2026-09-23).
PLAIN_MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


def verify_image_manifest(manifest: dict | list) -> None:
    """Require one plain linux/amd64 manifest, never an index, without downloading layers.

    ``manifest`` is ``docker manifest inspect --verbose`` output: an object for a plain
    manifest, a list of objects for an OCI index or Docker manifest list.
    """
    if not isinstance(manifest, dict):
        raise ValueError(
            "published version image must be a plain linux/amd64 manifest, not an index"
        )
    descriptor = manifest.get("Descriptor", {})
    if descriptor.get("mediaType") not in PLAIN_MANIFEST_TYPES:
        raise ValueError(
            f"published version image has media type {descriptor.get('mediaType')!r}, "
            "not a plain image manifest"
        )
    platform = descriptor.get("platform", {})
    if (platform.get("os"), platform.get("architecture")) != ("linux", "amd64"):
        raise ValueError("published version image must be linux/amd64")
    print(
        "Version image is a plain linux/amd64 manifest; layers/runtime not tested here"
    )


if __name__ == "__main__":
    try:
        document = json.loads(Path(sys.argv[2]).read_text())
        if sys.argv[1] == "--image-manifest":
            verify_image_manifest(document)
        else:
            verify_assets(sys.argv[1], document)
    except (ValueError, OSError, KeyError) as exc:
        sys.exit(f"release assets: {exc}")

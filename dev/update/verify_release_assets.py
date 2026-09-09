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


if __name__ == "__main__":
    try:
        verify_assets(sys.argv[1], json.loads(Path(sys.argv[2]).read_text()))
    except (ValueError, OSError, KeyError) as exc:
        sys.exit(f"release assets: {exc}")

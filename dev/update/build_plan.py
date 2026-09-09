#!/usr/bin/env python3
"""Resolve build identities without mutating public version or update metadata."""

import argparse
import json
import os
from pathlib import Path
import re


def build_plan(
    root: Path, mode: str, ref: str, sha: str, image_tag: str = ""
) -> dict[str, str]:
    """Require a matching stable tag for publication; internal tags identify source."""
    if mode not in {"build", "internal", "release"}:
        raise ValueError("mode must be build, internal or release")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("source SHA must be a full 40-character commit")
    version = json.loads((root / "desktop/package.json").read_text())["version"]
    python_version = re.search(
        r'^__version__\s*=\s*"([^"]+)"', (root / "tit/__init__.py").read_text(), re.M
    )
    if not python_version:
        raise ValueError("tit/__init__.py has no version")
    lock = json.loads((root / "desktop/package-lock.json").read_text())
    runtime_versions = [
        version,
        python_version[1],
        lock.get("version"),
        lock.get("packages", {}).get("", {}).get("version"),
    ]
    if not version or any(value != version for value in runtime_versions):
        raise ValueError(
            f"runtime package and lock versions must agree: {runtime_versions}"
        )
    if mode in {"internal", "release"}:
        compose = re.search(
            r"image: idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-([^}]+)\}",
            (root / "docker-compose.yml").read_text(),
        )
        wheel_image = re.search(
            r'BUILTIN_SPEC = StackSpec\(\s*image="idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-([^}]+)\}"',
            (root / "tit/launch.py").read_text(),
        )
    if mode == "release":
        if not re.fullmatch(
            r"refs/tags/v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", ref
        ):
            raise ValueError(
                "release mode requires a stable vX.Y.Z tag, never a branch"
            )
        expected = ref.removeprefix("refs/tags/v")
        metadata_version = re.search(
            r'^__version__\s*=\s*"([^"]+)"', (root / "version.py").read_text(), re.M
        )
        versions = [
            version,
            python_version[1],
            metadata_version[1] if metadata_version else None,
            compose[1] if compose else None,
            wheel_image[1] if wheel_image else None,
            lock.get("version"),
            lock.get("packages", {}).get("", {}).get("version"),
        ]
        if any(value != expected for value in versions):
            raise ValueError(
                f"release version sites must all equal {expected}: {versions}"
            )
        if not (root / f"docs/releases/v{version}.md").is_file():
            raise ValueError("release requires authored docs/releases/vX.Y.Z.md")
    if mode == "internal":
        prepared_tag = compose[1] if compose else ""
        if (
            not re.fullmatch(r"internal-[A-Za-z0-9][A-Za-z0-9.-]{0,110}", prepared_tag)
            or wheel_image is None
            or wheel_image[1] != prepared_tag
            or (image_tag and image_tag != prepared_tag)
        ):
            raise ValueError(
                "internal handoff requires the selected image tag to match both docker-compose.yml and tit/launch.py BUILTIN_SPEC; prepare and commit the same internal-* cohort tag in both source defaults first"
            )
        image_tag = prepared_tag
    if image_tag and (
        mode == "release"
        or not re.fullmatch(r"internal-[A-Za-z0-9][A-Za-z0-9.-]{0,110}", image_tag)
    ):
        raise ValueError("image tag override is only allowed for internal-* builds")
    return {
        "mode": mode,
        "version": version,
        "python_version": python_version[1],
        "image_tag": version if mode == "release" else image_tag or f"internal-{sha}",
        "sha": sha,
    }


def stage_compose(content: str, image_tag: str) -> str:
    """Pin the CI installer's fallback to the image produced by the same workflow."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}", image_tag):
        raise ValueError("invalid image tag")
    staged, count = re.subn(
        r"image: idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-[^}]+\}",
        f"image: idossha/ti-toolbox:${{TIT_IMAGE_TAG:-{image_tag}}}",
        content,
    )
    if count != 1:
        raise ValueError("compose must contain exactly one toolbox image default")
    return staged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--image-tag", default="")
    parser.add_argument(
        "--stage-compose",
        action="store_true",
        help="CI only: stage this build image default for packaging",
    )
    args = parser.parse_args()
    try:
        result = build_plan(
            Path(__file__).resolve().parents[2],
            args.mode,
            args.ref,
            args.sha,
            args.image_tag,
        )
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"build plan: {exc}\n")
    if args.stage_compose:
        compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
        compose.write_text(stage_compose(compose.read_text(), result["image_tag"]))
    print(json.dumps(result, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in result.items()))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Update runtime versions without implicitly publishing release notes.

Internal: --version X.Y.Z-dev.N --development [--dry-run]
Release metadata: --version X.Y.Z [--dry-run]
Public docs (explicit): --version X.Y.Z --publish-notes --notes-file notes.md
Existing authored version pages and changelog entries are preserved.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Set by main(). Every writer in this module checks it before opening a file for writing.
DRY_RUN = False


def _write(file_path, content):
    """Write unless --dry-run. Returns True if the file was (or would be) changed."""
    if DRY_RUN:
        print(f"Would update: {file_path}")
        return True
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated: {file_path}")
    return True


def update_file_content(file_path, patterns):
    """Update patterns in a file"""

    if not os.path.exists(file_path):
        print(f"Skipped (not found): {file_path}")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    if content != original_content:
        return _write(file_path, content)
    print(f"No changes needed: {file_path}")
    return False


def update_version(new_version):
    """Update version across all project files"""
    print(f"Updating version to {new_version}")
    print("=" * 50)

    release_date = datetime.now().strftime("%B %d, %Y")

    # Files to update with their patterns
    files_to_update = {
        "version.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
            (
                r'(TI_CSC_INFO = \{\s*"version": )"[^"]*"',
                rf'\g<1>"{new_version}"',
            ),
            (r'"release_date": "[^"]*"', f'"release_date": "{release_date}"'),
            (
                r'"tag": "idossha/(?:simnibs|ti-toolbox):[^"]*"',
                f'"tag": "idossha/ti-toolbox:{new_version}"',
            ),
        ],
        "docs/_config.yml": [
            (r'version: "[^"]*"', f'version: "{new_version}"'),
        ],
        # THE run spec, and the only compose file in the repository (it moved here from
        # desktop/docker/docker-compose.v3.yml; the v2 two-service root compose it replaced is
        # gone, which is why there is no longer an idossha/simnibs bump here — nor in
        # dev/loader/docker-compose.dev.yml, which now carries dev *overrides* only and names no
        # image at all).
        #
        # v3 streamlined stack (docs/dev/ARCHITECTURE.md; docs/dev/HISTORY.md 2026-09-03): one image,
        # idossha/ti-toolbox:<ver>, tagged independently of idossha/simnibs (the v3 image bundles a
        # specific SimNIBS build, it does not share its version number).
        # The `:-dev` default is deliberately for local iteration only — bump it on every
        # release so a fresh `docker-compose.yml` pull with no TIT_IMAGE_TAG override resolves to
        # the version being released, not last release's dev tag.
        "docker-compose.yml": [
            (
                r"image: idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-[^}]*\}",
                f"image: idossha/ti-toolbox:${{TIT_IMAGE_TAG:-{new_version}}}",
            ),
        ],
        # Installed wheels have no root compose file, so the fallback must move with it.
        "tit/launch.py": [
            (
                r'(BUILTIN_SPEC = StackSpec\(\s*image="idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-)[^}]+',
                rf"\g<1>{new_version}",
            ),
        ],
        # v3 desktop app (desktop/). This is the number electron-builder writes into the app
        # bundle, the DMG/EXE/AppImage file names, and `app.getVersion()`; the release workflow
        # refuses to build when it disagrees with the tag. `-dev`/`-rc` suffixes are matched too so
        # a pre-release version can be promoted.
        "desktop/package.json": [
            (
                r'"version": "\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?"',
                f'"version": "{new_version}"',
            ),
        ],
        # Python package version
        "tit/__init__.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
        ],
        # Software citation metadata
        # Software citation metadata. Anchored on a leading newline so
        # "version:" does not also match "cff-version:".
        "CITATION.cff": [
            (r"\nversion: [^\n]*", f"\nversion: {new_version}"),
            (
                r"\ndate-released: [^\n]*",
                f'\ndate-released: "{datetime.now().strftime("%Y-%m-%d")}"',
            ),
        ],
    }

    update_desktop_lock(new_version)

    # Update dataset description JSON files
    update_dataset_descriptions(new_version)

    updated_files = []

    for file_path, patterns in files_to_update.items():
        if update_file_content(file_path, patterns):
            updated_files.append(file_path)

    print("\n" + "=" * 50)
    print(f"Version update complete!")
    print(f"Updated {len(updated_files)} core files:")
    for file_path in updated_files:
        print(f"   • {file_path}")


def update_dataset_descriptions(new_version):
    """Update Docker image versions in dataset description JSON files"""
    print(f"\nUpdating dataset description JSON files...")

    dataset_descriptions_dir = "resources/dataset_descriptions"

    # Find all JSON files in the dataset_descriptions directory
    json_files = [
        f for f in os.listdir(dataset_descriptions_dir) if f.endswith(".json")
    ]

    updated_count = 0
    for json_file in json_files:
        file_path = os.path.join(dataset_descriptions_dir, json_file)

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Update only the SimNIBS Docker image tag (dynamically based on new version)
        # Pattern to match Docker image tags in the JSON files
        patterns = [
            (
                r'"Tag": "idossha/(?:simnibs|ti-toolbox):[^"]*"',
                f'"Tag": "idossha/ti-toolbox:{new_version}"',
            ),
        ]

        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        # Previously this rewrote (and reported) every file whether or not the substitution
        # changed anything, while `updated_count` was never incremented and always printed 0.
        if content != original_content:
            _write(file_path, content)
            updated_count += 1

    print(f"Updated {updated_count} dataset description JSON files")


def add_release_to_changelog(version, release_notes=""):
    """Add a new release entry to both releases page and changelog"""
    release_date = datetime.now().strftime("%B %d, %Y")

    update_releases_page(version, release_notes, release_date)
    update_changelog_file(version, release_notes, release_date)
    create_individual_version_file(version, release_notes, release_date)
    update_navigation(version)
    update_previous_release_titles(version)


def update_releases_page(version, release_notes, release_date):
    """Update the main releases page"""
    releases_file = "docs/releases/releases.md"

    new_release_section = f"""### v{version} (Latest Release)

**Release Date**: {release_date}

{release_notes}

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-{version}.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-{version}-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-{version}.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-{version}.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/ti-toolbox_{version}_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/ti-toolbox:{version}`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{{{ site.baseurl }}}}/installation/)."""

    with open(releases_file, "r", encoding="utf-8") as f:
        content = f.read()

    # The "Latest Release" page shows ONLY the newest release, never the
    # full history (that's what changelog.md and the individual vX.md pages
    # are for). Keep the front matter and the trailing "## Getting Help"
    # section; replace everything else with just the new release section.
    front_matter_match = re.match(r"^(---\n.*?\n---\n)", content, flags=re.DOTALL)
    front_matter = front_matter_match.group(1) if front_matter_match else ""

    getting_help_match = re.search(r"(\n## Getting Help.*\Z)", content, flags=re.DOTALL)
    getting_help = getting_help_match.group(1) if getting_help_match else ""

    new_content = f"{front_matter}\n{new_release_section}\n\n---\n{getting_help}"

    _write(releases_file, new_content)
    print(f"Updated latest release in {releases_file}")


def update_changelog_file(version, release_notes, release_date):
    """Update the changelog file"""
    changelog_file = "docs/releases/changelog.md"

    new_changelog_section = f"""### v{version} (Latest Release)

**Release Date**: {release_date}

{release_notes}

#### Download Links

**Desktop App (v{version}):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/ti-toolbox_{version}_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/ti-toolbox:{version}`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---
"""

    with open(changelog_file, "r", encoding="utf-8") as f:
        content = f.read()

    if re.search(rf"^### v{re.escape(version)}(?: |$)", content, re.M):
        print(f"Preserved existing changelog entry: v{version}")
        return

    # Remove "(Latest Release)" from the current latest version to demote it
    content = re.sub(r"### v(\d+\.\d+\.\d+) \(Latest Release\)", r"### v\1", content)

    # Insert new release section after the front matter (after the first ---)
    lines = content.split("\n")
    insert_index = -1
    for i, line in enumerate(lines):
        if line.strip() == "---" and i > 5:  # Find the first --- after the front matter
            insert_index = i + 1
            break

    if insert_index > 0:
        # Split the new section into lines and insert them, preserving the
        # blank lines that separate sections so the entry matches the rest.
        new_lines = new_changelog_section.split("\n")
        for new_line in reversed(new_lines):
            lines.insert(insert_index, new_line)

        _write(changelog_file, "\n".join(lines))
        print(f"Updated changelog in {changelog_file}")
    else:
        print(f"Could not find insertion point in changelog")


def create_individual_version_file(version, release_notes, release_date):
    """Create an individual version file for the release"""
    version_file = f"docs/releases/v{version}.md"

    if Path(version_file).exists():
        print(f"Preserved authored release page: {version_file}")
        return

    version_content = f"""---
layout: releases
title: ""
nav_title: "Release v{version}"
permalink: /releases/v{version}/
nav_exclude: true
sitemap: false
---

# Release v{version}

**Release Date**: {release_date}

{release_notes}

#### Download Links

**Desktop App (v{version}):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-{version}.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/ti-toolbox_{version}_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/ti-toolbox:{version}`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{{{ site.baseurl }}}}/installation/).

---

## Getting Help

If you encounter issues with this release:

1. Check the [Installation Guide]({{{{ site.baseurl }}}}/installation/) for setup instructions
2. Review the [Troubleshooting]({{{{ site.baseurl }}}}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
"""

    _write(version_file, version_content)
    print(f"Created individual version file: {version_file}")


def update_navigation(version):
    """Update the Releases sidebar nav data (docs/_data/nav.yml)"""
    nav_file = "docs/_data/nav.yml"

    with open(nav_file, "r", encoding="utf-8") as f:
        content = f.read()

    current_latest_pattern = r"Latest \(v[\d\.]+\)"
    new_latest = f"Latest (v{version})"
    content = re.sub(current_latest_pattern, new_latest, content)

    if f"/releases/v{version}/" in content:
        print(f"Version v{version} already in releases nav")
    else:
        # Insert the new version right after the "Version History" group marker
        version_line = f"    - {{ title: v{version}, url: /releases/v{version}/ }}"
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "group: Version History" in line:
                lines.insert(i + 1, version_line)
                break
        content = "\n".join(lines)

    _write(nav_file, content)


def update_previous_release_titles(version):
    """Remove 'Latest Release' from previous version files and ensure nav_exclude"""
    releases_dir = "docs/releases"

    # Get all version files except the current one
    version_files = [
        f
        for f in os.listdir(releases_dir)
        if f.startswith("v") and f.endswith(".md") and f != f"v{version}.md"
    ]

    for version_file in version_files:
        file_path = os.path.join(releases_dir, version_file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            updated_content = content

            # Remove "(Latest Release)" from title and update format to hide from navigation
            updated_content = re.sub(
                r"title: v(\d+\.\d+\.\d+) \(Latest Release\)",
                r'title: ""\nnav_title: "Release v\1"',
                updated_content,
            )

            # Also handle existing Release titles
            updated_content = re.sub(
                r"title: Release v(\d+\.\d+\.\d+)",
                r'title: ""\nnav_title: "Release v\1"',
                updated_content,
            )

            # Ensure nav_exclude is present
            if "nav_exclude: true" not in updated_content:
                # Add nav_exclude after permalink
                updated_content = re.sub(
                    r"(permalink: /releases/v\d+\.\d+\.\d+/)\n",
                    r"\1\nnav_exclude: true\n",
                    updated_content,
                )

            if updated_content != content:
                _write(file_path, updated_content)

        except Exception as e:
            print(f"Could not update {version_file}: {e}")


def update_desktop_lock(version: str) -> None:
    """Keep only the lockfile root package in step; dependency versions stay untouched."""
    path = Path("desktop/package-lock.json")
    lock = json.loads(path.read_text())
    lock["version"] = version
    lock["packages"][""]["version"] = version
    content = json.dumps(lock, indent=2) + "\n"
    if content != path.read_text():
        _write(path, content)


def update_development_version(version: str) -> None:
    """Stamp runtime packages without announcing a public release or changing image defaults."""
    update_file_content(
        "desktop/package.json", [(r'"version": "[^"]*"', f'"version": "{version}"')]
    )
    update_desktop_lock(version)
    update_file_content(
        "tit/__init__.py", [(r'__version__ = "[^"]*"', f'__version__ = "{version}"')]
    )


def main():
    """Separate runtime version changes from explicit public release documentation changes."""
    global DRY_RUN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="X.Y.Z, or X.Y.Z-dev.N with --development"
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help="only runtime versions; preserve public release metadata",
    )
    parser.add_argument(
        "--publish-notes",
        action="store_true",
        help="update public release landing page and navigation",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        help="authored Markdown notes, required with --publish-notes",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    pattern = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    if args.development:
        pattern += r"-dev\.(?:0|[1-9]\d*)"
    if not re.fullmatch(pattern, args.version):
        parser.error("expected X.Y.Z-dev.N for development or stable X.Y.Z for release")
    if args.development and (args.publish_notes or args.notes_file):
        parser.error("development mode cannot publish release notes")
    if args.publish_notes != bool(args.notes_file):
        parser.error("--publish-notes and --notes-file must be supplied together")
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else None
    if notes is not None and not notes.strip():
        parser.error("release notes must not be empty")
    DRY_RUN = args.dry_run
    os.chdir(Path(__file__).resolve().parents[2])
    if args.development:
        update_development_version(args.version)
    else:
        update_version(args.version)
        if notes is not None:
            add_release_to_changelog(args.version, notes)
    print(
        "Dry run complete; no writes."
        if DRY_RUN
        else "Review the version diff. No commit, tag or publication was performed."
    )


if __name__ == "__main__":
    main()

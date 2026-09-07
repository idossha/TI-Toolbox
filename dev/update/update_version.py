#!/usr/bin/env python3
"""
Version Update Script for Temporal Interference Toolbox

Updates every place a version number is written, so a tag and the artifacts built from it agree.
`release-v3.yml`'s `plan` job re-checks a subset of these and refuses to release when they drift,
so a site missed here becomes a red release rather than a mislabelled artifact.

Usage:
    python dev/update/update_version.py                     # interactive, writes
    python dev/update/update_version.py --version 3.0.0     # non-interactive, writes
    python dev/update/update_version.py --version 3.0.0 --dry-run
    python dev/update/update_version.py --dry-run           # asks for the version, writes nothing

--dry-run prints every file that WOULD change (and the substitutions it would make) and touches
nothing on disk. It is the way to answer "did this script get taught about the new file?" without
dirtying the tree.
"""

import argparse
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
            (r'"version": "[^"]*"', f'"version": "{new_version}"'),
            (r'"release_date": "[^"]*"', f'"release_date": "{release_date}"'),
            (
                r'"tag": "idossha/simnibs:[^"]*"',
                f'"tag": "idossha/simnibs:v{new_version}"',
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
        # v3 desktop app (desktop/). This is the number electron-builder writes into the app
        # bundle, the DMG/EXE/AppImage file names, and `app.getVersion()`; the release workflow
        # refuses to build when it disagrees with the tag. `-dev`/`-rc` suffixes are matched too so
        # a pre-release version can be promoted.
        "desktop/package.json": [
            (r'"version": "\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?"', f'"version": "{new_version}"'),
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
                r'\ndate-released: [^\n]*',
                f'\ndate-released: "{datetime.now().strftime("%Y-%m-%d")}"',
            ),
        ],
    }

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

    print(f"\n Additional automated updates:")
    print(f"   • Updated main releases page (docs/releases/releases.md)")
    print(f"   • Updated changelog (docs/releases/changelog.md)")
    print(f"   • Created individual release page (docs/releases/v{new_version}.md)")
    print(f"   • Updated releases nav (docs/_data/nav.yml)")
    print(f"   • Updated previous release titles")
    print(
        f"   • Updated dataset description JSON files with new SimNIBS Docker image version"
    )
    print(f"   • Updated the v3 desktop app version (desktop/package.json)")
    print(f"   • Updated Python package version (tit/__init__.py)")


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
                r'"Tag": "idossha/simnibs:[^"]*"',
                f'"Tag": "idossha/simnibs:v{new_version}"',
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
- Docker Image: `docker pull idossha/simnibs:latest`
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
- Docker Image: `docker pull idossha/simnibs:v{version}`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---
"""

    with open(changelog_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove "(Latest Release)" from the current latest version to demote it
    content = re.sub(
        r"### v(\d+\.\d+\.\d+) \(Latest Release\)", r"### v\1", content
    )

    # Insert new release section after the front matter (after the first ---)
    lines = content.split("\n")
    insert_index = -1
    for i, line in enumerate(lines):
        if (
            line.strip() == "---" and i > 5
        ):  # Find the first --- after the front matter
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
- Docker Image: `docker pull idossha/simnibs:v{version}`
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


def get_release_info():
    """Interactive prompt to collect release information"""
    print("\nRelease Information Collection")
    print("=" * 50)

    while True:
        version = input("\nEnter version number (e.g., 2.0.1): ").strip()
        if re.match(r"^\d+\.\d+\.\d+$", version):
            break
        print("Invalid version format. Please use X.Y.Z format (e.g., 2.0.1)")

    print("\n Additions (Enter each addition on a new line, press Enter twice when done):")
    additions = []
    while True:
        line = input().strip()
        if not line and additions:  # Empty line and we have at least one addition
            break
        if line:  # Only add non-empty lines
            additions.append(line)

    print("\n Fixes (Enter each fix on a new line, press Enter twice when done):")
    fixes = []
    while True:
        line = input().strip()
        if not line and fixes:  # Empty line and we have at least one fix
            break
        if line:  # Only add non-empty lines
            fixes.append(line)

    # Format the release notes
    release_notes = []
    release_notes.append("#### Additions")
    release_notes.append("")
    if additions:
        release_notes.extend(f"- {add}" for add in additions)
    else:
        release_notes.append("- N/A")

    release_notes.append("")
    release_notes.append("#### Fixes")
    release_notes.append("")
    if fixes:
        release_notes.extend(f"- {fix}" for fix in fixes)
    else:
        release_notes.append("- N/A")

    return version, "\n".join(release_notes)


def main():
    """Main function"""
    global DRY_RUN

    parser = argparse.ArgumentParser(
        description="Update the version number everywhere it is written.",
        epilog=(
            "With no --version the script prompts for the version and the release notes. "
            "--dry-run writes nothing and prints every file it would touch."
        ),
    )
    parser.add_argument("--version", help="new version, X.Y.Z (skips the interactive prompt)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would change; do not write any file",
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    # chdir first: every path in this module is relative to the repository root.
    os.chdir(Path(__file__).parent.parent.parent)  # dev/update/ -> dev/ -> root

    if args.version:
        if not re.match(r"^\d+\.\d+\.\d+$", args.version):
            parser.error(f"invalid version {args.version!r}; expected X.Y.Z")
        new_version = args.version
        # Non-interactive: the release-notes prompt would hang in CI. A dry run only needs to show
        # which files move, and a real non-interactive run gets its notes from docs/releases/.
        release_notes = "#### Additions\n\n- N/A\n\n#### Fixes\n\n- N/A"
    else:
        new_version, release_notes = get_release_info()

    if DRY_RUN:
        print("\n*** DRY RUN — no file will be written ***\n")

    update_version(new_version)

    add_release_to_changelog(new_version, release_notes)

    if DRY_RUN:
        print("\nDry run complete. Nothing was written.")
        return

    print("\nNext steps (the full procedure is docs/dev/RELEASE.md):")
    print(f"   1. Review all changes: git diff")
    print(f"   2. Commit the changes: git commit -m 'chore: release v{new_version}'")
    print(f"   3. Create a release tag: git tag v{new_version}")
    print(f"   4. Push changes: git push && git push --tags")
    print(f"   5. Watch .github/workflows/release-v3.yml — it builds and pushes the Docker image,")
    print(f"      validates unsigned desktop artifacts, then signs, notarises and publishes them.")
    print(f"\nRelease documentation automatically updated:")
    print(f"   • Main releases page shows v{new_version} as latest")
    print(f"   • Changelog includes full release history")
    print(f"   • Releases sidebar updated with v{new_version} in version history")
    print(f"   • Individual release page created with proper links")
    print(f"   • Dataset description JSON files updated with new SimNIBS Docker image version")
    print(f"   • Docker Compose files updated with new image tags")
    print(f"   • v3 desktop app version updated (desktop/package.json)")


if __name__ == "__main__":
    main()

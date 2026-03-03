#!/usr/bin/env python3
"""
Version Update Script for Temporal Interference Toolbox
This script updates version information across all project files.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path


def update_file_content(file_path, patterns):
    """Update patterns in a file"""

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    if content != original_content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated: {file_path}")
        return True
    else:
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
        "docker-compose.yml": [
            (r"image: idossha/simnibs:[\S]+", f"image: idossha/simnibs:v{new_version}"),
            (r'TI_TOOLBOX_VERSION: "[\S]+"', f'TI_TOOLBOX_VERSION: "v{new_version}"'),
        ],
        "dev/bash_dev/docker-compose.dev.yml": [
            (r"image: idossha/simnibs:[\S]+", f"image: idossha/simnibs:v{new_version}")
        ],
        # Electron Desktop App files
        "package/package.json": [
            (r'"version": "\d+\.\d+\.\d+"', f'"version": "{new_version}"'),
        ],
        "package/src/index.html": [
            (r"TI-Toolbox V\d+\.\d+\.\d+", f"TI-Toolbox V{new_version}"),
        ],
        "package/docker/docker-compose.yml": [
            (
                r"image: idossha/simnibs:v[\d\.]+",
                f"image: idossha/simnibs:v{new_version}",
            ),
            (
                r'TI_TOOLBOX_VERSION: "v[\d\.]+"',
                f'TI_TOOLBOX_VERSION: "v{new_version}"',
            ),
        ],
        # Python package version
        "tit/__init__.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
        ],
        # Electron app project metadata version
        "package/src/main.js": [
            (r"version: '[^']*'", f"version: '{new_version}'"),
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
    print(f"   • Updated releases sidebar navigation (docs/_layouts/releases.html)")
    print(f"   • Updated previous release titles")
    print(
        f"   • Updated dataset description JSON files with new SimNIBS Docker image version"
    )
    print(
        f"   • Updated Electron Desktop App (package.json, index.html, docker-compose.yml, main.js)"
    )
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

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated: {file_path}")

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
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/TT-Toolbox-{version}.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{{{ site.baseurl }}}}/installation/)."""

    with open(releases_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace the current latest release section
    pattern = r"### v\d+\.\d+\.\d+ \(Latest Release\).*?(?=---|\n##|\Z)"

    new_content = re.sub(pattern, new_release_section, content, flags=re.DOTALL)

    with open(releases_file, "w", encoding="utf-8") as f:
        f.write(new_content)

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
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TT-Toolbox-{version}.deb)

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
        # Split the new section into lines and insert them
        new_lines = new_changelog_section.split("\n")
        for i, new_line in enumerate(reversed(new_lines)):
            if new_line.strip():  # Only insert non-empty lines
                lines.insert(insert_index, new_line)

        new_content = "\n".join(lines)
        with open(changelog_file, "w", encoding="utf-8") as f:
            f.write(new_content)
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
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TT-Toolbox-{version}.deb)

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

    with open(version_file, "w", encoding="utf-8") as f:
        f.write(version_content)
    print(f"Created individual version file: {version_file}")


def update_navigation(version):
    """Update the releases sidebar navigation in the releases layout"""
    layout_file = "docs/_layouts/releases.html"

    with open(layout_file, "r", encoding="utf-8") as f:
        content = f.read()

    current_latest_pattern = r"Latest \(v[\d\.]+\)"
    new_latest = f"Latest (v{version})"
    content = re.sub(current_latest_pattern, new_latest, content)

    # Add new version to the version history section
    # Find the line with the first version link and add the new version before it
    version_link = f"        <li><a href=\"{{{{ site.baseurl }}}}/releases/v{version}/\" {{% if page.url == '/releases/v{version}/' or page.url == '/TI-Toolbox/releases/v{version}/' %}}class=\"active\"{{% endif %}}>v{version}</a></li>"

    if f"/releases/v{version}/" in content:
        print(f"Version v{version} already in releases sidebar")
        return

    # Find the first version link in the history and insert new version before it
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "<h4>Version History</h4>" in line:
            # Insert the new version link after the "Version History" header
            lines.insert(i + 1, version_link)
            break

    new_content = "\n".join(lines)
    with open(layout_file, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated releases sidebar navigation in {layout_file}")



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
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                print(f"Updated {version_file}")

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
    if additions:
        release_notes.extend(f"- {add}" for add in additions)
    else:
        release_notes.append("- N/A")

    release_notes.append("")
    release_notes.append("#### Fixes")
    if fixes:
        release_notes.extend(f"- {fix}" for fix in fixes)
    else:
        release_notes.append("- N/A")

    return version, "\n".join(release_notes)


def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h", "help"]:
        print("Usage: python update_version_new.py")
        print("\nThis script will guide you through the version update process:")
        print("  1. Enter the new version number")
        print("  2. List additions (one per line)")
        print("  3. List fixes (one per line)")
        print("\nThe script will then update all necessary files and create release notes.")
        sys.exit(0)

    new_version, release_notes = get_release_info()

    script_dir = Path(__file__).parent.parent.parent  # Go up to project root (dev/update/ -> dev/ -> root)
    os.chdir(script_dir)

    update_version(new_version)

    add_release_to_changelog(new_version, release_notes)

    print("\nNext steps:")
    print(f"   1. Review all changes: git diff")
    print(f"   2. Commit the changes: git add . && git commit -m 'Release v{new_version}'")
    print(f"   3. Create a release tag: git tag v{new_version}")
    print(f"   4. Push changes: git push && git push --tags")
    print(f"   5. Build and push Docker image to Docker Hub")
    print(f"   6. Create GitHub release at: https://github.com/idossha/TI-Toolbox/releases/new")
    print(f"\nRelease documentation automatically updated:")
    print(f"   • Main releases page shows v{new_version} as latest")
    print(f"   • Changelog includes full release history")
    print(f"   • Releases sidebar updated with v{new_version} in version history")
    print(f"   • Individual release page created with proper links")
    print(f"   • Dataset description JSON files updated with new SimNIBS Docker image version")
    print(f"   • Docker Compose files updated with new image tags")
    print(f"   • Electron Desktop App files updated (package.json, index.html, docker-compose.yml)")


if __name__ == "__main__":
    main()

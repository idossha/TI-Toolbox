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
    if not os.path.exists(file_path):
        print(f"⚠️  Warning: {file_path} not found")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated: {file_path}")
            return True
        else:
            print(f"ℹ️  No changes needed: {file_path}")
            return False
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False

def update_version(new_version):
    """Update version across all project files"""
    print(f"🚀 Updating version to {new_version}")
    print("=" * 50)
    
    release_date = datetime.now().strftime("%B %d, %Y")
    
    # Files to update with their patterns
    files_to_update = {
        "version.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
            (r'"version": "[^"]*"', f'"version": "{new_version}"'),
            (r'"release_date": "[^"]*"', f'"release_date": "{release_date}"'),
        ],
        
        "launcher/executable/src/ti_csc_launcher.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
        ],
        
        "launcher/executable/src/dialogs.py": [
            (r'__version__ = "[^"]*"', f'__version__ = "{new_version}"'),
        ],
        
        "docs/_config.yml": [
            (r'version: "[^"]*"', f'version: "{new_version}"'),
        ]
    }
    
    updated_files = []
    
    for file_path, patterns in files_to_update.items():
        if update_file_content(file_path, patterns):
            updated_files.append(file_path)
    
    print("\n" + "=" * 50)
    print(f"🎉 Version update complete!")
    print(f"📝 Updated {len(updated_files)} files:")
    for file_path in updated_files:
        print(f"   • {file_path}")

def add_release_to_changelog(version, release_notes=""):
    """Add a new release entry to the releases page"""
    releases_file = "docs/releases/releases.md"
    
    if not os.path.exists(releases_file):
        print(f"⚠️  Warning: {releases_file} not found")
        return
    
    release_date = datetime.now().strftime("%B %d, %Y")
    
    # Convert release notes to bullet points if they're not already
    if not release_notes.strip().startswith('-'):
        release_notes = '\n'.join(f'- {note.strip()}' for note in release_notes.split('.') if note.strip())
    
    new_release_entry = f"""### v{version}

**Release Date**: {release_date}

#### Major Changes
{release_notes}

#### Installation
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TemporalInterferenceToolbox-Linux-x86_64.AppImage)
- [Bash Script & Compose YAML](https://github.com/idossha/TI-Toolbox/tree/main/launcher/bash) (for command-line/remote use)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

"""
    
    try:
        with open(releases_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the marker and insert the new release
        marker = "<!-- DO NOT MODIFY: Auto-generated release content will be appended here -->"
        if marker in content:
            parts = content.split(marker, 1)
            new_content = f"{parts[0]}{marker}\n\n{new_release_entry}{parts[1]}"
            
            with open(releases_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ Added release entry to {releases_file}")
        else:
            print(f"⚠️  Could not find insertion marker in {releases_file}")
    
    except Exception as e:
        print(f"❌ Error updating releases file: {e}")

def main():
    """Main function"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("Usage: python update_version.py <new_version> [release_notes]")
        print("Example: python update_version.py 2.1.0 'Added new features and bug fixes'")
        print("\nThis script updates version information across all project files:")
        print("  • version.py")
        print("  • launcher/executable/src/ti_csc_launcher.py")
        print("  • launcher/executable/src/dialogs.py")
        print("  • docs/_config.yml")
        print("  • docs/releases/releases.md")
        sys.exit(0)
    
    new_version = sys.argv[1]
    release_notes = sys.argv[2] if len(sys.argv) > 2 else ""
    
    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        print("❌ Error: Version must be in format X.Y.Z (e.g., 2.1.0)")
        sys.exit(1)
    
    # Change to script directory
    script_dir = Path(__file__).parent.parent.parent  # Go up one more level to reach project root
    os.chdir(script_dir)
    
    # Update version in all files
    update_version(new_version)
    
    # Add release to changelog if release notes provided
    if release_notes:
        add_release_to_changelog(new_version, release_notes)
        print("\n💡 Next steps:")
        print(f"   1. Review the changes: git diff")
        print(f"   2. Commit the changes: git add . && git commit -m 'Release v{new_version}'")
        print(f"   3. Create a release tag: git tag v{new_version}")
        print(f"   4. Push changes: git push && git push --tags")
        print(f"   5. Create a GitHub release at: https://github.com/idossha/TI-Toolbox/releases/new")

if __name__ == "__main__":
    main() 
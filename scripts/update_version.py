#!/usr/bin/env python3
"""
Version Update Script for Temporal Interference Toolbox
This script updates version information across all project files.
"""

import os
import re
import sys
import glob
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
    
    release_date = datetime.now().strftime("%Y-%m-%d")
    release_month_year = datetime.now().strftime("%B %Y")
    
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
        
        "docs/index.md": [
            (r'\*\*Version [^*]*\*\*', f'**Version {new_version}**'),
            (r'Released [A-Za-z]+ \d{4}', f'Released {release_month_year}'),
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
    
    print(f"\n💡 Next steps:")
    print(f"   1. Review the changes: git diff")
    print(f"   2. Commit the changes: git add . && git commit -m 'Update version to {new_version}'")
    print(f"   3. Create a release tag: git tag v{new_version}")
    print(f"   4. Push changes: git push && git push --tags")
    print(f"   5. Create a GitHub release at: https://github.com/idossha/TI-Toolbox/releases/new")

def add_release_to_changelog(version, release_notes=""):
    """Add a new release entry to the releases page"""
    releases_file = "docs/releases.md"
    
    if not os.path.exists(releases_file):
        print(f"⚠️  Warning: {releases_file} not found")
        return
    
    release_date = datetime.now().strftime("%B %Y")
    
    new_release_entry = f"""
<div class="release">
  <div class="release-header">
    <h2>Version {version}</h2>
    <span class="release-date">{release_date}</span>
  </div>
  
  <p><strong>Latest Release</strong></p>
  
  <h3>📋 Release Notes</h3>
  <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
    <p>{release_notes if release_notes else "No release notes provided."}</p>
  </div>
  
  <div class="release-downloads">
    <a href="https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TemporalInterferenceToolbox-macOS-universal.zip">macOS</a>
    <a href="https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TemporalInterferenceToolbox-Linux-x86_64.AppImage">Linux</a>
    <a href="https://github.com/idossha/TI-Toolbox/releases/download/v{version}/TI-Toolbox-Windows.exe">Windows</a>
  </div>
</div>

"""
    
    try:
        with open(releases_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the position to insert the new release (after the header)
        marker = "All notable changes and releases are documented below."
        if marker in content:
            parts = content.split(marker, 1)
            new_content = parts[0] + marker + new_release_entry + parts[1]
            
            with open(releases_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ Added release entry to {releases_file}")
        else:
            print(f"⚠️  Could not find insertion point in {releases_file}")
    
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
        print("  • docs/index.md")
        print("  • docs/_config.yml")
        sys.exit(0)
    
    new_version = sys.argv[1]
    release_notes = sys.argv[2] if len(sys.argv) > 2 else ""
    
    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        print("❌ Error: Version must be in format X.Y.Z (e.g., 2.1.0)")
        sys.exit(1)
    
    # Change to script directory
    script_dir = Path(__file__).parent.parent
    os.chdir(script_dir)
    
    # Update version in all files
    update_version(new_version)
    
    # Add release to changelog if release notes provided
    if release_notes:
        add_release_to_changelog(new_version, release_notes)

if __name__ == "__main__":
    main() 
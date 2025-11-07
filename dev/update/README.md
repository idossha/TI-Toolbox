# CI/CD and Release Management

This directory contains scripts and workflows for managing releases and deployments of the Temporal Interference Toolbox.

## 🚀 Release Process

### Option 1: Automated CI/CD Release (Recommended)

1. **Update version locally**:
   ```bash
   python scripts/update_version.py 2.1.0 "Added new features and bug fixes"
   ```

2. **Review and commit changes**:
   ```bash
   git diff  # Review changes
   git add .
   git commit -m "Update version to 2.1.0"
   git tag v2.1.0
   git push && git push --tags
   ```

3. **Create GitHub Release**:
   - Go to: https://github.com/idossha/TI-Toolbox/releases/new
   - Select the tag you just created (v2.1.0)
   - Add release title and description
   - Click "Publish release"

4. **Automatic Actions**:
   - ✅ Builds executables for macOS, Windows, and Linux
   - ✅ Updates website with new version information
   - ✅ Uploads downloadable assets to the release
   - ✅ Deploys updated website to GitHub Pages

## 📁 Files and Workflows

### `.github/workflows/release.yml`
Main CI/CD workflow that:
- **Triggers**: On GitHub release publication or manual dispatch
- **Builds**: Cross-platform executables using your `build.py` script
- **Updates**: Website version information automatically
- **Uploads**: Release assets to GitHub releases

### `.github/workflows/deploy-docs.yml`
Documentation deployment workflow that:
- **Triggers**: When docs/ folder changes are pushed to main
- **Deploys**: Website to GitHub Pages using Jekyll

### `development/update/update_version.py`
Python script that updates version across all project files:
- `version.py` - Main version file
- `launcher/executable/src/ti_csc_launcher.py` - Launcher app
- `launcher/executable/src/dialogs.py` - Dialog components
- `docs/` files - Website content

## 🔧 How It Works

### Build Process
1. **Cross-platform builds**: Uses GitHub Actions runners for macOS, Windows, and Ubuntu
2. **Python environment**: Sets up Python 3.9 with required dependencies
3. **Your build script**: Runs your existing `launcher/executable/build.py`
4. **Asset naming**: Creates consistently named executables:
   - `TemporalInterferenceToolbox-macOS-universal.zip`
   - `TemporalInterferenceToolbox-Windows-x64.exe`
   - `TemporalInterferenceToolbox-Linux-x86_64.AppImage`

### Website Updates
1. **Version extraction**: Gets version from release tag or manual input
2. **Content updates**: Updates version references in:
   - Homepage (`docs/index.md`)
   - Downloads page (`docs/downloads.md`)
   - Releases page (`docs/releases.md`)
   - Jekyll config (`docs/_config.yml`)
3. **Auto-commit**: Commits changes back to repository
4. **Jekyll deployment**: GitHub Pages builds and deploys automatically

### Download Links
The workflow automatically updates download links to point to:
```
https://github.com/idossha/TI-Toolbox/releases/download/v{VERSION}/TemporalInterferenceToolbox-{PLATFORM}.{EXT}
```

## 🛠️ Setup Requirements

### GitHub Repository Settings
1. **Actions**: Ensure GitHub Actions are enabled
2. **Pages**: Set up GitHub Pages to deploy from Actions
3. **Permissions**: Workflows have required permissions for:
   - Reading repository content
   - Writing to Pages
   - Uploading release assets

### Local Development
- Python 3.8+ for running the version update script
- Git for version control and tagging

## 🔍 Monitoring

- **Actions tab**: Monitor workflow progress at https://github.com/idossha/TI-Toolbox/actions
- **Releases**: View published releases at https://github.com/idossha/TI-Toolbox/releases
- **Website**: Check deployed site at https://idossha.github.io/TI-Toolbox/

## 🐛 Troubleshooting

### Build Failures
- Check the Actions tab for detailed error logs
- Ensure all required files exist in `launcher/executable/`
- Verify Python dependencies in requirements files

### Website Not Updating
- Check if the docs deployment workflow ran
- Verify GitHub Pages settings point to Actions source
- Clear browser cache or check in incognito mode

### Version Conflicts
- Ensure version numbers follow semantic versioning (X.Y.Z)
- Check that all files were updated consistently
- Verify git tags match release versions 

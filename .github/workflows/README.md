# GitHub Actions Workflows

## Release Build Workflow

The `release-build.yml` workflow automatically builds the TI-Toolbox Electron app for all supported platforms when a new release is published.

### Supported Platforms

The workflow builds for the following platforms:

1. **macOS Intel (x64)** - DMG and ZIP
2. **macOS Silicon (arm64)** - DMG and ZIP  
3. **Windows (x64)** - NSIS installer and portable executable
4. **Linux (x64)** - AppImage and DEB package

### Trigger Events

The workflow is triggered by:

- **Release Published**: Automatically builds and uploads artifacts when you publish a new GitHub release
- **Manual Trigger**: Can be manually triggered from the Actions tab for testing

### How to Create a Release

1. **Update the version** in `package/package.json`:
   ```json
   {
     "version": "2.3.0"
   }
   ```

2. **Create a new tag**:
   ```bash
   git tag v2.3.0
   git push origin v2.3.0
   ```

3. **Create a GitHub Release**:
   - Go to your repository on GitHub
   - Click on "Releases" → "Draft a new release"
   - Select the tag you just created (v2.3.0)
   - Add release notes
   - Click "Publish release"

4. **Automatic Build**: The workflow will automatically start building for all platforms

5. **Download Artifacts**: Once complete, the built installers will be attached to your release

### Build Artifacts

Each platform produces the following artifacts:

#### macOS Intel
- `TI-Toolbox-{version}.dmg` - DMG installer
- `TI-Toolbox-{version}-mac.zip` - ZIP archive

#### macOS Silicon  
- `TI-Toolbox-{version}-arm64.dmg` - DMG installer (Apple Silicon)
- `TI-Toolbox-{version}-arm64-mac.zip` - ZIP archive (Apple Silicon)

#### Windows
- `TI-Toolbox Setup {version}.exe` - NSIS installer
- `TI-Toolbox {version}.exe` - Portable executable

#### Linux
- `TI-Toolbox-{version}.AppImage` - AppImage (universal)
- `ti-toolbox_{version}_amd64.deb` - Debian package

### Manual Testing

To test the workflow without creating a release:

1. Go to the "Actions" tab in your GitHub repository
2. Select "Build and Release Electron App" workflow
3. Click "Run workflow"
4. Select the branch to run from
5. Click "Run workflow"

The artifacts will be available in the workflow run page (but won't be attached to a release).

### Requirements

- Node.js 18+ (automatically installed by the workflow)
- Valid `package/package.json` with electron-builder configuration
- Required assets:
  - `package/assets/icon.icns` (macOS)
  - `package/assets/icon.ico` (Windows)
  - `package/assets/icon.png` (Linux)
- `package/build/entitlements.mac.plist` (macOS signing)

### Troubleshooting

#### Build Fails

1. Check the workflow logs in the Actions tab
2. Verify all required files exist:
   - `package/package.json`
   - `package/assets/*` (icons)
   - `package/build/entitlements.mac.plist`

#### Artifacts Not Uploaded

1. Check if the release was created properly
2. Verify the `GITHUB_TOKEN` has permissions (should be automatic)
3. Check the "release" job logs

#### Wrong Version Number

1. Update `version` in `package/package.json`
2. Commit and push changes
3. Delete the old tag and recreate it:
   ```bash
   git tag -d v2.3.0
   git push origin :refs/tags/v2.3.0
   git tag v2.3.0
   git push origin v2.3.0
   ```

### Notes

- **Code Signing**: The workflow does not include code signing. For production releases, you should add:
  - macOS: Apple Developer certificate and notarization
  - Windows: Code signing certificate
  
- **Build Time**: Each platform takes approximately 5-10 minutes to build
  
- **Parallel Builds**: All platforms build in parallel to save time

- **Caching**: npm dependencies are cached to speed up subsequent builds

### Adding Code Signing (Future Enhancement)

For macOS code signing, you would need to add:

```yaml
- name: Import Code Signing Certificate (macOS)
  if: matrix.platform == 'mac'
  env:
    CERTIFICATE_BASE64: ${{ secrets.MACOS_CERTIFICATE }}
    CERTIFICATE_PASSWORD: ${{ secrets.MACOS_CERTIFICATE_PASSWORD }}
  run: |
    # Import certificate from secrets
    # Configure electron-builder to sign
```

For Windows code signing:

```yaml
- name: Sign Windows Executable
  if: matrix.platform == 'win'
  env:
    WINDOWS_CERTIFICATE: ${{ secrets.WINDOWS_CERTIFICATE }}
  run: |
    # Sign the executable
```


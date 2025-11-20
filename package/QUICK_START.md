# Quick Start Guide

Get up and running with the TI-Toolbox Desktop App in 3 simple steps!

## Prerequisites Check

Before you begin, make sure you have:

- [ ] **Docker Desktop** installed and running
- [ ] **X Server** installed for your platform:
  - macOS: XQuartz
  - Windows: VcXsrv or Xming
  - Linux: X11 (usually pre-installed)

## Step 1: Build the Application

```bash
# Navigate to the package directory
cd TI-Toolbox/package

# Install dependencies
npm install

# Build for your platform
npm run build
```

**Platform-Specific Builds**:
```bash
npm run build:mac      # macOS only
npm run build:win      # Windows only
npm run build:linux    # Linux only
```

## Step 2: Run the Application

After building:

- **macOS**: Open `dist/mac/TI-Toolbox.app`
- **Windows**: Run `dist/TI-Toolbox-Setup-{version}.exe` or `dist/TI-Toolbox {version}.exe`
- **Linux**: Run `dist/TI-Toolbox-{version}.AppImage` or install the `.deb` package

## Step 3: Launch TI-Toolbox

1. Click **Browse** to select your project directory
2. Click **Launch TI-Toolbox**
3. Wait for the GUI to appear
4. Monitor the **Activity** feed (log link + Stop button live during a session)
5. Start working with TI-Toolbox!

---

## Development Mode

Want to test without building?

```bash
npm start
```

This runs the app directly from source - perfect for development and testing!

---

## Troubleshooting

### "Docker daemon not running"
→ Start Docker Desktop and wait for it to fully initialize

### "X Server connection failed" (macOS)
→ Open XQuartz → Preferences → Security → Enable "Allow connections from network clients"

### "Build failed"
→ Delete `node_modules` and `dist`, then run:
```bash
rm -rf node_modules dist
npm install
npm run build
```

---

## Need Help?

- Full documentation: See `README.md`
- Issues: https://github.com/idossha/TI-Toolbox/issues
- Documentation: https://idossha.github.io/TI-Toolbox/

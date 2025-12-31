# TI-Toolbox Desktop App Architecture

## Overview

The TI-Toolbox Desktop Application is an Electron-based launcher that encapsulates the Docker-based TI-Toolbox workflow, providing a user-friendly desktop experience across macOS, Windows, and Linux.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    TI-Toolbox Desktop App                       │
│                         (Electron)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────┐         ┌──────────────────────┐         │
│  │  Renderer Process │ ◄─IPC─► │   Main Process       │         │
│  │  (UI Layer)       │         │   (Backend Logic)    │         │
│  └───────────────────┘         └──────────────────────┘         │
│          │                              │                       │
│          │                              ▼                       │
│    [index.html]                  [Docker Client]                │
│    [styles.css]                         │                       │
│    [renderer.js]                        │                       │
│                                         │                       │
└─────────────────────────────────────────┼───────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │     Docker Desktop              │
                        │  (Container Runtime)            │
                        └─────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │  docker-compose.yml             │
                        │  • freesurfer_container         │
                        │  • simnibs_container            │
                        └─────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │  SimNIBS Container              │
                        │  • TI-Toolbox GUI (PyQt5)       │
                        │  • X11 Forwarding               │
                        └─────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │  User's Project Directory       │
                        │  (BIDS-compliant structure)     │
                        └─────────────────────────────────┘
```

## Component Breakdown

### 1. Electron Application

#### Main Process (`src/main.js`)
- **Responsibilities**:
  - Window management
  - Docker orchestration
  - File system operations
  - IPC communication with renderer
  - Platform-specific setup (X11, XQuartz, VcXsrv)
  - Structured logging / diagnostics broadcasting

- **Supporting Modules**:
  - `backend/docker-manager.js`: wraps Docker CLI + API (`dockerode`) for lifecycle control and GUI exec streaming
  - `backend/env.js`: resolves runtime environment (DISPLAY/TZ) and manages `xhost` permissions
  - `backend/project-service.js`: project validation plus BIDS initialization
  - `backend/config-store.js`: simple JSON persistence for user preferences
  - `backend/logger.js`: configures `electron-log` destinations

- **Key Flows**:
  - `check-docker`: Verifies CLI/Compose availability, pings Docker API, reports existing containers
  - `start-toolbox`: Validates project, ensures DISPLAY permissions, starts the Compose stack, launches GUI exec
  - `stop-toolbox`: Gracefully tears down containers (triggered by UI or shutdown hooks)
  - Real-time status events (`launcher-progress`, `launcher-log`) fan out to renderer

#### Renderer Process (`src/renderer.js`)
- **Responsibilities**:
  - User interface logic
  - User input validation
  - Status updates and progress display
  - Communication with main process via IPC
  - Displays rolling activity feed + log location
  - Offers manual stop control and log reveal button

- **UI Components**:
  - Project directory selector
  - Docker status indicator
  - Platform-specific warnings
  - Launch + Stop controls with progress display
  - Diagnostics module (log path, activity timeline)

#### UI Layer (`src/index.html`, `src/styles.css`)
- Clean, modern interface
- Responsive design
- Platform-aware messaging
- Visual feedback for all operations

### 2. Docker Integration

#### Container Orchestration
- **dockerode** is used for:
  - CLI/API health checks (`docker version`, `docker compose version`, `docker.ping()`)
  - Discovering TI-Toolbox containers and streaming logs
  - Executing the GUI launcher script inside `simnibs_container`
- **docker compose** CLI is still leveraged for multi-service lifecycle:
- A copy of `docker-compose.yml` ships inside `package/docker/`, and packaged builds bundle it under `resources/docker/`, so the launcher works even when the original repository is unavailable.

```javascript
// Volume creation
docker volume create ti-toolbox_freesurfer_data

// Start services (build + detached)
docker compose -f docker-compose.yml up --build -d

// Cleanup (triggered when GUI closes or Stop button pressed)
docker compose -f docker-compose.yml down --remove-orphans
```

#### Environment Variables
Sets required environment for container:
- `LOCAL_PROJECT_DIR`: User's project directory
- `PROJECT_DIR_NAME`: Project directory name
- `DISPLAY`: X11 display configuration
- `TZ`: Host timezone
- `COMPOSE_PROJECT_NAME`: Docker Compose project name

### 3. Platform-Specific Handling

#### macOS
```javascript
// X11 Server: XQuartz
DISPLAY = "host.docker.internal:0"

// XQuartz configuration
defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false
xhost +localhost
xhost +$(hostname)
```

#### Linux
```javascript
// X11 Server: Native
DISPLAY = process.env.DISPLAY || ":0"

// X11 permissions
xhost +local:root
xhost +local:docker
```

#### Windows
```javascript
// X11 Server: VcXsrv/Xming
DISPLAY = "host.docker.internal:0"

// Path conversion
Windows path → Docker-compatible path
C:\Users\... → /c/Users/...
```

### 4. Project Initialization Flow

```
User selects directory
        │
        ▼
Check if initialized (.initialized marker)
        │
        ├─► Yes → Use existing project
        │
        └─► No → Create structure:
                 ├─ code/tit/config/
                 ├─ derivatives/ti-toolbox/.ti-toolbox-info/
                 ├─ derivatives/freesurfer/
                 ├─ derivatives/SimNIBS/
                 └─ sourcedata/
```

## Data Flow

### Launch Sequence

```
1. User clicks "Launch TI-Toolbox"
        │
        ▼
2. Check Docker availability
        │
        ▼
3. Initialize project structure (if new)
        │
        ▼
4. Platform-specific X11 setup
        │
        ▼
5. Create Docker volumes
        │
        ▼
6. Start Docker Compose services
        │
        ▼
7. Wait for container initialization (3s)
        │
        ▼
8. Execute GUI launcher in container
        │
        ▼
9. User interacts with TI-Toolbox GUI
        │
        ▼
10. User closes GUI
        │
        ▼
11. Cleanup: Stop containers, revert X11 permissions
```

### IPC Communication

```javascript
// Renderer → Main
'get-saved-path'      → Returns last used project directory
'select-directory'    → Opens directory picker dialog
'check-docker'        → Verifies Docker availability
'start-toolbox'       → Launches full stack (non-blocking)
'stop-toolbox'        → Stops containers immediately
'get-platform'        → Returns current OS platform
'get-log-path'        → Resolves the log file path
'reveal-log-file'     → Opens Finder/Explorer at the log location

// Main → Renderer
'launcher-progress'   → Structured status updates (preflight, compose, GUI lifecycle, cleanup)
'launcher-log'        → Tail output from the GUI exec stream
```

## File System Structure

### Desktop App Files
```
package/
├── src/                      # Source code
│   ├── main.js              # Main process
│   ├── renderer.js          # Renderer process
│   ├── index.html           # UI markup
│   └── styles.css           # UI styles
├── assets/                   # Application assets
│   ├── icon.png             # Base icon
│   ├── icon.icns            # macOS icon
│   └── icon.ico             # Windows icon
├── build/                    # Build configuration
│   └── entitlements.mac.plist
├── dist/                     # Built applications (generated)
├── package.json             # NPM configuration
└── README.md                # Documentation
```

### User Project Structure (BIDS)
```
project/
├── code/
│   └── tit/
│       └── config/
│           └── .initialized
├── derivatives/
│   ├── tit/
│   │   └── .tit-info/
│   ├── freesurfer/
│   └── SimNIBS/
└── sourcedata/
```

## Security Considerations

### Code Signing (macOS)
- Uses entitlements for JIT compilation and unsigned libraries
- Required for SimNIBS Python environment
- Configured in `build/entitlements.mac.plist`

### X11 Security
- Temporary permission grant for container access
- Permissions reverted on application exit
- Platform-specific security models respected

### Docker Permissions
- No elevated privileges required
- Uses user's existing Docker installation
- Project directory mounted with user permissions

## Build Process

### Electron Builder
```
Source Files
    │
    ▼
Electron Builder
    │
    ├─► macOS:
    │   ├─ .app bundle
    │   ├─ .dmg installer
    │   └─ .zip archive
    │
    ├─► Windows:
    │   ├─ .exe installer (NSIS)
    │   └─ .exe portable
    │
    └─► Linux:
        ├─ .AppImage
        └─ .deb package
```

### Build Configuration
- Defined in `package.json` under `build`
- Platform-specific targets and architectures
- Icon conversion and code signing
- Installer customization

## Extension Points

### Future Enhancements
1. **Preset Management**: Save/load common configurations
2. **Update Checker**: Auto-update functionality
3. **Docker Image Management**: Pull/update images from UI
4. **Project Templates**: Quick-start project templates
5. **Log Viewer**: View container logs in UI
6. **Advanced Settings**: Docker resources, network settings
7. **Multi-Project**: Switch between projects without relaunch

## Dependencies

### Runtime Dependencies
- **Electron**: Desktop framework
- **Node.js**: JavaScript runtime
- None in production (all bundled)

### External Requirements
- **Docker Desktop**: Container runtime
- **X Server**: GUI display (platform-specific)

## Performance Considerations

- **Startup Time**: ~3 seconds for container initialization
- **Memory Usage**: ~200MB (app) + Docker containers
- **Disk Space**: ~50MB (app) + Docker images (~5GB)
- **Background Activity**: Minimal when GUI closed

## Maintenance

### Version Updates
1. Update `version` in `package.json`
2. Update version display in `src/index.html`
3. Rebuild application
4. Test on all platforms

### Icon Updates
1. Replace `assets/icon.png`
2. Regenerate platform-specific icons
3. Rebuild application

### Docker Integration Updates
- Update `docker-compose.yml` path if moved
- Update container names if changed
- Update environment variables if modified

## Troubleshooting

### Debug Mode
Run in development with console:
```bash
npm start
```

### Logs
- **Electron logs**: Console output
- **Docker logs**: `docker logs simnibs_container`
- **Build logs**: `dist/*.log`

### Common Issues
1. **Docker not found**: Check Docker Desktop installation
2. **X Server issues**: Platform-specific X11 configuration
3. **Permission errors**: Docker daemon access rights
4. **Build failures**: Node modules cache corruption

## References

- Electron Documentation: https://www.electronjs.org/docs
- Docker Documentation: https://docs.docker.com/
- TI-Toolbox Wiki: https://idossha.github.io/TI-Toolbox/

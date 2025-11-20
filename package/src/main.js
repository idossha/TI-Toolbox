const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { configureLogger, logger } = require('./backend/logger');
const {
  buildRuntimeEnv,
  ensureDisplayAccess,
  resetDisplayAccess,
  patchProcessPathEnv
} = require('./backend/env');
const { validateProjectDirectory, initializeProject } = require('./backend/project-service');
const DockerManager = require('./backend/docker-manager');
const ConfigStore = require('./backend/config-store');

let mainWindow = null;
let dockerManager = null;
let configStore = null;
let toolboxRoot = null;
let runtimeEnv = null;
let shuttingDown = false;

function composeExists(candidate) {
  if (!candidate) {
    return false;
  }
  return fs.existsSync(path.join(candidate, 'docker-compose.yml'));
}

function findComposeUpwards(startDir, maxDepth = 10) {
  if (!startDir) return null;
  let current = path.resolve(startDir);

  for (let i = 0; i < maxDepth; i += 1) {
    if (composeExists(current)) {
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  return null;
}

function getEmbeddedDockerRoot() {
  const candidates = [];

  // In packaged apps, extraResources are in the resources folder
  if (process.resourcesPath) {
    candidates.push(path.join(process.resourcesPath, 'docker'));
    candidates.push(path.join(process.resourcesPath, 'app.asar.unpacked', 'docker'));
  }

  const appPath = app.getAppPath();
  candidates.push(path.join(appPath, 'docker'));
  candidates.push(path.join(path.dirname(appPath), 'docker'));

  const exeDir = path.dirname(app.getPath('exe'));
  
  // For macOS, resources are in Contents/Resources
  if (process.platform === 'darwin') {
    candidates.push(path.join(exeDir, '..', 'Resources', 'docker'));
    candidates.push(path.join(exeDir, '..', '..', 'Resources', 'docker'));
  }
  
  // For Windows/Linux
  candidates.push(path.join(exeDir, 'resources', 'docker'));
  candidates.push(path.join(path.resolve(exeDir, '..'), 'Resources', 'docker'));
  candidates.push(path.join(exeDir, 'docker'));
  
  // Development paths
  candidates.push(path.join(process.cwd(), 'docker'));
  candidates.push(path.join(__dirname, '..', 'docker'));
  
  // Log all candidates for debugging
  logger.info('Looking for docker directory in:', candidates);

  for (const candidate of candidates) {
    if (composeExists(candidate)) {
      logger.info(`Found docker directory at: ${candidate}`);
      return path.resolve(candidate);
    }
  }

  logger.error('Docker directory not found in any candidate location');
  return null;
}

function resolveToolboxRoot() {
  if (process.env.TI_TOOLBOX_ROOT) {
    const envRoot = path.resolve(process.env.TI_TOOLBOX_ROOT);
    if (composeExists(envRoot)) {
      return envRoot;
    }
  }

  if (!app.isPackaged) {
    const devRoot = path.resolve(__dirname, '..', '..');
    const foundDev = findComposeUpwards(devRoot);
    return foundDev || devRoot;
  }

  const startPoints = [
    app.getAppPath(),
    process.resourcesPath,
    path.dirname(app.getPath('exe')),
    path.resolve(path.dirname(app.getPath('exe')), '..'),
    process.cwd()
  ];

  for (const start of startPoints) {
    const found = findComposeUpwards(start);
    if (found) {
      return found;
    }
  }

  const embedded = getEmbeddedDockerRoot();
  if (embedded) {
    return embedded;
  }

  return path.resolve(process.cwd());
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 700,
    resizable: true,
    maximizable: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: path.join(__dirname, '../assets/icon.png'),
    title: 'TI-Toolbox Launcher'
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.setMenuBarVisibility(false);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function forwardDockerEvents() {
  if (!dockerManager) {
    return;
  }

  dockerManager.on('progress', (payload) => {
    mainWindow?.webContents?.send('launcher-progress', payload);
  });

  dockerManager.on('log', (message) => {
    mainWindow?.webContents?.send('launcher-log', { message, timestamp: new Date().toISOString() });
  });

  dockerManager.on('gui-exited', async () => {
    runtimeEnv = null;
    await resetDisplayAccess().catch(() => {});
  });
}

async function startApplication() {
  configureLogger(app);
  patchProcessPathEnv();
  configStore = new ConfigStore(app);
  await configStore.load();

  toolboxRoot = resolveToolboxRoot();
  logger.info(`TI-Toolbox root resolved to: ${toolboxRoot}`);
  
  // Verify docker-compose.yml exists
  const composeFile = path.join(toolboxRoot, 'docker-compose.yml');
  if (!fs.existsSync(composeFile)) {
    logger.error(`docker-compose.yml not found at ${composeFile}`);
    // Try to find it in embedded location
    const embedded = getEmbeddedDockerRoot();
    if (embedded) {
      toolboxRoot = embedded;
      logger.info(`Using embedded docker root: ${toolboxRoot}`);
    }
  }
  
  dockerManager = new DockerManager(toolboxRoot);
  forwardDockerEvents();
  createWindow();
}

async function gracefulShutdown() {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;

  if (dockerManager) {
    await dockerManager.stop(runtimeEnv?.env ?? process.env).catch(() => {});
  }

  await resetDisplayAccess().catch(() => {});
}

app.whenReady().then(() => {
  startApplication();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', async () => {
  if (process.platform !== 'darwin') {
    await gracefulShutdown();
    app.quit();
  }
});

app.on('before-quit', async (event) => {
  if (!shuttingDown) {
    event.preventDefault();
    await gracefulShutdown();
    app.quit();
  }
});

process.on('SIGINT', async () => {
  await gracefulShutdown();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await gracefulShutdown();
  process.exit(0);
});

// IPC handlers
ipcMain.handle('get-saved-path', () => {
  return configStore?.get('projectDir', '') ?? '';
});

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory']
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

ipcMain.handle('check-docker', async () => {
  if (!dockerManager) {
    return { available: false, error: 'Docker manager not initialized yet.' };
  }

  try {
    const cliVersion = await dockerManager.verifyDockerApi();
    await dockerManager.verifyComposeCli();
    await dockerManager.pingApi();
    const existingContainers = await dockerManager.getExistingContainers();

    return {
      available: true,
      version: cliVersion,
      existingContainers
    };
  } catch (error) {
    logger.error('Docker check failed', error);
    return { available: false, error: error.message };
  }
});

ipcMain.handle('start-toolbox', async (_event, projectDir) => {
  if (!dockerManager) {
    return { success: false, error: 'Docker manager not initialized.' };
  }

  try {
    const validatedDir = await validateProjectDirectory(projectDir);
    await configStore.save({ projectDir: validatedDir });

    const initResult = await initializeProject(validatedDir);
    runtimeEnv = buildRuntimeEnv(validatedDir);

    await ensureDisplayAccess();
    await dockerManager.prepareStack(runtimeEnv.env);
    await dockerManager.launchGui(runtimeEnv.env);

    return { success: true, isNewProject: initResult.created };
  } catch (error) {
    logger.error('Failed to launch TI-Toolbox', error);
    await dockerManager.stop(runtimeEnv?.env ?? process.env).catch(() => {});
    await resetDisplayAccess().catch(() => {});
    runtimeEnv = null;

    return { success: false, error: error.message };
  }
});

ipcMain.handle('stop-toolbox', async () => {
  if (!dockerManager) {
    return { success: false, error: 'Docker manager not initialized.' };
  }

  try {
    await dockerManager.stop(runtimeEnv?.env ?? process.env);
    await resetDisplayAccess();
    runtimeEnv = null;
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('get-platform', () => os.platform());

ipcMain.handle('get-log-path', () => {
  const logFile = logger?.transports?.file?.getFile?.();
  return logFile?.path ?? '';
});

ipcMain.handle('reveal-log-file', async () => {
  const logPath = logger?.transports?.file?.getFile?.().path;
  if (!logPath) {
    return { success: false, error: 'Log file not available' };
  }

  await shell.showItemInFolder(logPath);
  return { success: true };
});


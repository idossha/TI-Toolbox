const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs-extra');
const os = require('os');
const { configureLogger, logger } = require('./backend/logger');
const {
  buildRuntimeEnv,
  ensureDisplayAccess,
  resetDisplayAccess,
  patchProcessPathEnv,
  checkWindowsXServer
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
  const iconPath = path.join(__dirname, '../assets/icon.png');
  logger.info(`Using icon: ${iconPath}`);
  
  mainWindow = new BrowserWindow({
    width: 800,
    height: 700,
    resizable: false,
    maximizable: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: iconPath,
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
    logger.info(`Runtime env set:`, { runtimeEnv: !!runtimeEnv, hasEnv: !!(runtimeEnv && runtimeEnv.env) });

    if (!runtimeEnv || !runtimeEnv.env) {
      throw new Error('Failed to build runtime environment for Windows');
    }

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

ipcMain.handle('check-xserver', async () => {
  if (os.platform() !== 'win32') {
    return { available: true, message: 'X server check not needed on this platform' };
  }

  try {
    const result = await checkWindowsXServer();
    return result;
  } catch (error) {
    logger.error('X server check failed:', error);
    return { available: false, error: error.message };
  }
});

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

ipcMain.handle('create-new-project', async (_event, projectDir, includeExampleData) => {
  if (!projectDir) {
    return { success: false, error: 'Project directory is required.' };
  }

  try {
    // Create the project directory structure
    const validatedDir = await validateProjectDirectory(projectDir);
    
    // Initialize BIDS structure
    const initResult = await initializeProject(validatedDir);
    
    // If user wants example data, we need to copy it
    if (includeExampleData) {
      const { spawn } = require('child_process');
      const exampleDataScript = path.join(
        toolboxRoot,
        'tit',
        'new_project',
        'example_data_manager.py'
      );
      
      // Check if the script exists
      if (fs.existsSync(exampleDataScript)) {
        // Run the Python script to copy example data
        await new Promise((resolve, reject) => {
          const pythonProcess = spawn('python3', [
            exampleDataScript,
            toolboxRoot,
            validatedDir
          ]);
          
          let stdout = '';
          let stderr = '';
          
          pythonProcess.stdout.on('data', (data) => {
            stdout += data.toString();
          });
          
          pythonProcess.stderr.on('data', (data) => {
            stderr += data.toString();
          });
          
          pythonProcess.on('close', (code) => {
            if (code === 0) {
              logger.info('Example data copied successfully');
              resolve();
            } else {
              logger.error(`Example data copy failed: ${stderr}`);
              // Don't reject, just continue without example data
              resolve();
            }
          });
          
          pythonProcess.on('error', (err) => {
            logger.error(`Failed to run example data script: ${err.message}`);
            // Don't reject, just continue without example data
            resolve();
          });
        });
      } else {
        logger.warn('Example data script not found, skipping example data copy');
      }
    }
    
    // Copy configuration files
    const configSrcDir = path.join(toolboxRoot, 'tit', 'new_project', 'configs');
    const configDstDir = path.join(validatedDir, 'code', 'ti-toolbox', 'config');
    
    if (fs.existsSync(configSrcDir)) {
      await fs.copy(configSrcDir, configDstDir, { overwrite: false });
      logger.info('Copied configuration files to new project');
    }
    
    // Create dataset_description.json if it doesn't exist
    const datasetDescPath = path.join(validatedDir, 'dataset_description.json');
    if (!fs.existsSync(datasetDescPath)) {
      const datasetDesc = {
        "Name": `TI-Toolbox Project: ${path.basename(validatedDir)}`,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": ["TI-Toolbox User"],
        "Description": "TI-Toolbox project for temporal interference analysis",
        "License": "CC BY-NC 4.0",
        "ReferencesAndLinks": [
          "https://simnibs.github.io/",
          "https://github.com/idossha/TI-Toolbox"
        ]
      };
      await fs.writeJson(datasetDescPath, datasetDesc, { spaces: 2 });
      logger.info('Created dataset_description.json');
    }
    
    // Create README if it doesn't exist
    const readmePath = path.join(validatedDir, 'README');
    if (!fs.existsSync(readmePath)) {
      const projectName = path.basename(validatedDir);
      const readmeContent = `# ${projectName}

This is a BIDS-compliant neuroimaging dataset generated by TI-Toolbox for temporal interference (TI) stimulation modeling and analysis.

## Overview

This project contains structural MRI data and derivatives for simulating and analyzing temporal interference electric field patterns in the brain.

## Dataset Structure

- \`sourcedata/\` - Raw DICOM source files
- \`sub-*/\` - Subject-level BIDS-formatted neuroimaging data (NIfTI files)
- \`derivatives/\` - Processed data and analysis results
  - \`freesurfer/\` - FreeSurfer anatomical segmentation and surface reconstructions
  - \`SimNIBS/\` - SimNIBS head models and electric field simulations
  - \`ti-toolbox/\` - TI-Toolbox simulation results and analyses
- \`code/ti-toolbox/\` - Configuration files for the toolbox

## Software

Data processing and simulations were performed using:
- **TI-Toolbox** - Temporal interference modeling pipeline
- **FreeSurfer** - Cortical reconstruction and volumetric segmentation
- **SimNIBS** - Finite element modeling for electric field simulations

## More Information

For more information about TI-Toolbox, visit:
- GitHub: https://github.com/idossha/TI-Toolbox
- Documentation: https://idossha.github.io/TI-toolbox/

## BIDS Compliance

This dataset follows the Brain Imaging Data Structure (BIDS) specification for organizing and describing neuroimaging data. For more information about BIDS, visit: https://bids.neuroimaging.io/
`;
      await fs.writeFile(readmePath, readmeContent);
      logger.info('Created README file');
    }
    
    // Create project status file
    const statusDir = path.join(validatedDir, 'derivatives', 'ti-toolbox', '.ti-toolbox-info');
    const statusFile = path.join(statusDir, 'project_status.json');
    
    if (!fs.existsSync(statusFile)) {
      const statusData = {
        project_created: new Date().toISOString(),
        last_updated: new Date().toISOString(),
        config_created: true,
        example_data_copied: includeExampleData,
        user_preferences: {
          show_welcome: true
        },
        project_metadata: {
          name: path.basename(validatedDir),
          path: validatedDir,
          version: '2.2.3'
        }
      };
      
      if (includeExampleData) {
        statusData.example_subjects = ['sub-ernie', 'sub-MNI152'];
        statusData.example_data_timestamp = new Date().toISOString();
      }
      
      await fs.ensureDir(statusDir);
      await fs.writeJson(statusFile, statusData, { spaces: 2 });
      logger.info('Created project status file');
    }
    
    await configStore.save({ projectDir: validatedDir });
    
    return { 
      success: true, 
      projectDir: validatedDir,
      exampleDataCopied: includeExampleData 
    };
  } catch (error) {
    logger.error('Failed to create new project', error);
    return { success: false, error: error.message };
  }
});


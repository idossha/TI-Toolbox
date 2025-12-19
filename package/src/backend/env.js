const os = require('os');
const path = require('path');
const { logger } = require('./logger');
const { getExeca } = require('./execa');

const DEFAULT_PATHS = [
  '/usr/local/bin',
  '/opt/homebrew/bin',
  '/usr/bin',
  '/bin',
  '/usr/sbin',
  '/sbin',
  // Docker Desktop default locations
  '/Applications/Docker.app/Contents/Resources/bin',
  // Windows Docker paths
  'C:\\Program Files\\Docker\\Docker\\resources\\bin',
  'C:\\ProgramData\\DockerDesktop\\version-bin',
  // Linux additional paths
  '/snap/bin'
];

function ensurePathEnv(env = process.env) {
  if (!env) {
    logger.error('ensurePathEnv: env is null or undefined');
    env = process.env || {};
  }

  const separator = process.platform === 'win32' ? ';' : ':';
  const pathKeys = process.platform === 'win32' ? ['Path', 'PATH'] : ['PATH'];
  const currentValue = pathKeys.map(key => env[key]).find(Boolean) || '';
  const segments = currentValue.split(separator).filter(Boolean);

  // Add platform-specific paths
  const platformPaths = DEFAULT_PATHS.filter(dir => {
    if (process.platform === 'win32') {
      return dir.includes(':\\') || !dir.startsWith('/');
    }
    return !dir.includes(':\\');
  });

  platformPaths.forEach(dir => {
    if (!segments.includes(dir)) {
      segments.push(dir);
    }
  });

  const updatedValue = segments.join(separator);

  // Create a new object to avoid mutating the original
  const nextEnv = Object.assign({}, env);
  nextEnv.PATH = updatedValue;
  if (process.platform === 'win32') {
    nextEnv.Path = updatedValue;
  }

  logger.info(`Updated PATH: ${updatedValue}`);
  return nextEnv;
}

function patchProcessPathEnv() {
  const updated = ensurePathEnv(process.env);
  process.env.PATH = updated.PATH;
  if (updated.Path) {
    process.env.Path = updated.Path;
  }
  return process.env.PATH;
}

function getDisplayEnv() {
  switch (os.platform()) {
    case 'darwin':
      // For macOS with XQuartz, always use host.docker.internal
      // Docker containers cannot access the native macOS socket path
      logger.info('macOS detected, using host.docker.internal:0 for DISPLAY');
      return 'host.docker.internal:0';
    case 'win32':
      logger.info('Windows detected, using host.docker.internal:0 for DISPLAY');
      return 'host.docker.internal:0';
    default:
      // On Linux, use the existing DISPLAY or default to :0
      if (process.env.DISPLAY) {
        logger.info(`Linux detected, using existing DISPLAY: ${process.env.DISPLAY}`);
        return process.env.DISPLAY;
      }
      logger.info('Linux detected, using default DISPLAY: :0');
      return ':0';
  }
}

function convertWindowsPathToDockerFormat(winPath) {
  // Convert Windows paths to Docker Desktop format
  // Docker Desktop on Windows supports: C:/Users/name/project (preferred)
  // This is more reliable than WSL2 format /mnt/c/path
  // Reference: launcher/executable/src/ti_csc_launcher.py lines 900-912

  if (!winPath) {
    logger.error('convertWindowsPathToDockerFormat: received null/undefined path');
    return winPath;
  }

  logger.info(`[Path Conversion] Input: ${winPath}`);

  // If it's a Unix-style path (starts with / but not backslash), return as-is
  if (winPath.startsWith('/') && !winPath.includes('\\')) {
    logger.info(`[Path Conversion] Unix-style path, returning as-is: ${winPath}`);
    return winPath;
  }

  // Normalize: convert all backslashes to forward slashes
  // C:\Users\name\project -> C:/Users/name/project
  let normalizedPath = winPath.replace(/\\/g, '/');
  logger.info(`[Path Conversion] After normalization: ${normalizedPath}`);

  // Match Windows drive letter pattern: C:/ or C:
  const driveMatch = normalizedPath.match(/^([A-Za-z]):(.*)$/);

  if (!driveMatch) {
    logger.warn(`[Path Conversion] Does not match Windows drive pattern: ${winPath}`);
    logger.warn(`[Path Conversion] Returning normalized path`);
    return normalizedPath;
  }

  // Docker Desktop on Windows supports C:/path format directly
  const dockerPath = normalizedPath;

  logger.info(`[Path Conversion] Final Docker path: ${dockerPath}`);

  return dockerPath;
}

function getTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch (error) {
    logger.warn('Failed to determine timezone, defaulting to UTC', error);
    return 'UTC';
  }
}

function buildRuntimeEnv(projectDir) {
  const absoluteProjectDir = path.resolve(projectDir);
  const projectDirName = path.basename(absoluteProjectDir);

  logger.info('═══════════════════════════════════════════════════════');
  logger.info('Building Runtime Environment for Docker');
  logger.info('═══════════════════════════════════════════════════════');
  logger.info(`Platform: ${process.platform}`);
  logger.info(`Node.js Path Module: ${path.sep === '\\' ? 'Windows' : 'POSIX'}`);
  logger.info(`Original input path: ${projectDir}`);
  logger.info(`Absolute project path: ${absoluteProjectDir}`);
  logger.info(`Project directory name: ${projectDirName}`);

  // Convert Windows paths to Docker Desktop format for compatibility
  let dockerProjectDir;
  if (process.platform === 'win32') {
    logger.info('Windows detected - converting path for Docker Desktop...');
    dockerProjectDir = convertWindowsPathToDockerFormat(absoluteProjectDir);
  } else {
    logger.info('Non-Windows platform - using path as-is');
    dockerProjectDir = absoluteProjectDir;
  }

  logger.info(`Docker mount path (LOCAL_PROJECT_DIR): ${dockerProjectDir}`);
  logger.info(`Container path will be: /mnt/${projectDirName}`);

  const baseEnv = {
    ...process.env,
    LOCAL_PROJECT_DIR: dockerProjectDir,
    PROJECT_DIR_NAME: projectDirName,
    DISPLAY: getDisplayEnv(),
    TZ: getTimezone(),
    COMPOSE_PROJECT_NAME: 'ti-toolbox'
  };

  const env = ensurePathEnv(baseEnv);

  const result = {
    absoluteProjectDir,
    projectDirName,
    env
  };

  logger.info('───────────────────────────────────────────────────────');
  logger.info('Environment Variables Summary:');
  logger.info(`  LOCAL_PROJECT_DIR = ${result.env.LOCAL_PROJECT_DIR}`);
  logger.info(`  PROJECT_DIR_NAME = ${result.env.PROJECT_DIR_NAME}`);
  logger.info(`  DISPLAY = ${result.env.DISPLAY}`);
  logger.info(`  TZ = ${result.env.TZ}`);
  logger.info(`  Docker volume mount: ${result.env.LOCAL_PROJECT_DIR}:/mnt/${result.env.PROJECT_DIR_NAME}`);
  logger.info('═══════════════════════════════════════════════════════');

  return result;
}

async function checkWindowsXServer() {
  try {
    const execa = await getExeca();
    const env = ensurePathEnv(process.env);

    // Check for common X servers on Windows
    const xServerProcesses = [
      'vcxsrv', 'VcXsrv', 'XWin', 'xwin', 'Xming', 'xming'
    ];

    for (const processName of xServerProcesses) {
      try {
        // Use tasklist on Windows to check for running processes
        const { stdout } = await execa('tasklist', ['/FI', `IMAGENAME eq ${processName}.exe`, '/NH'], {
          env,
          reject: false,
          timeout: 5000
        });

        if (stdout && stdout.includes(`${processName}.exe`)) {
          logger.info(`Found running X server: ${processName}`);
          return { available: true, server: processName };
        }
      } catch (error) {
        // Continue checking other processes
        logger.debug(`Failed to check for ${processName}:`, error.message);
      }
    }

    // Try to check if we can connect to the display
    try {
      const { stdout } = await execa('powershell', [
        '-Command',
        'try { $client = New-Object System.Net.Sockets.TcpClient; $client.Connect("localhost", 6000); $client.Close(); "success" } catch { "failed" }'
      ], { env, reject: false, timeout: 3000 });

      if (stdout && stdout.trim() === 'success') {
        logger.info('X server connection test successful');
        return { available: true, server: 'unknown' };
      }
    } catch (error) {
      logger.debug('X server connection test failed:', error.message);
    }

    logger.warn('No X server detected on Windows');
    return { available: false, error: 'No X server (VcXsrv, Xming, etc.) appears to be running' };
  } catch (error) {
    logger.error('Failed to check Windows X server:', error);
    return { available: false, error: `Failed to check X server: ${error.message}` };
  }
}

async function ensureDisplayAccess() {
  const platform = os.platform();

  if (platform === 'darwin') {
    // Detect DISPLAY from launchd if not already set
    if (!process.env.DISPLAY) {
      await detectMacOSDisplay();
    }

    await ensureXQuartz();

    // Allow X11 connections - use simpler approach with timeout
    // Docker containers will use host.docker.internal:0 so we just need to allow network connections
    await allowXHost(['+']);

  } else if (platform === 'linux') {
    if (!process.env.DISPLAY) {
      process.env.DISPLAY = ':0';
    }
    await allowXHost(['+local:']);
  } else if (platform === 'win32') {
    // Always check if X server is running on Windows before launching
    logger.info('Performing X server check on Windows...');
    const xServerStatus = await checkWindowsXServer();
    if (!xServerStatus.available) {
      const errorMsg = xServerStatus.error || 'X server not detected';
      logger.error(`X server check failed: ${errorMsg}`);
      throw new Error(`X server is not running. Please start VcXsrv or another X server and try again. Details: ${errorMsg}`);
    }
    logger.info(`X server detected and running: ${xServerStatus.server || 'unknown'}`);
  }
}

async function resetDisplayAccess() {
  // Simplified - don't bother cleaning up xhost settings
  // They reset on XQuartz restart anyway
  logger.info('Skipping xhost cleanup');
}

async function detectMacOSDisplay() {
  try {
    const execa = await getExeca();
    const env = ensurePathEnv(process.env);
    
    // Try to get DISPLAY from launchctl
    const { stdout } = await execa('/bin/launchctl', ['getenv', 'DISPLAY'], { env, reject: false });
    if (stdout && stdout.trim()) {
      process.env.DISPLAY = stdout.trim();
      logger.info(`Detected DISPLAY from launchctl: ${process.env.DISPLAY}`);
      return;
    }
    
    // Check if XQuartz is running and get its display
    const fs = require('fs');
    const tmpDirs = fs.readdirSync('/tmp').filter(d => d.startsWith('com.apple.launchd.') && d.includes('org.xquartz'));
    if (tmpDirs.length > 0) {
      const displaySocket = `/tmp/${tmpDirs[0]}/org.xquartz:0`;
      if (fs.existsSync(displaySocket)) {
        process.env.DISPLAY = displaySocket;
        logger.info(`Detected XQuartz DISPLAY socket: ${process.env.DISPLAY}`);
        return;
      }
    }
    
    // Default fallback
    process.env.DISPLAY = ':0';
    logger.info('Using default DISPLAY: :0');
  } catch (error) {
    logger.warn('Failed to detect DISPLAY, using :0', error);
    process.env.DISPLAY = ':0';
  }
}

async function ensureXQuartz() {
  try {
    const env = ensurePathEnv(process.env);
    const execa = await getExeca();
    
    // Use absolute paths for commands to work when launched from GUI
    const { exitCode } = await execa('/usr/bin/pgrep', ['-x', 'XQuartz'], { env, reject: false });
    if (exitCode !== 0) {
      logger.info('Starting XQuartz…');
      await execa('/usr/bin/open', ['-a', 'XQuartz'], { env });
      
      // Configure XQuartz for Docker compatibility using absolute path
      await execa('/usr/bin/defaults', ['write', 'org.macosforge.xquartz.X11', 'nolisten_tcp', '-bool', 'false'], { env });
      await execa('/usr/bin/defaults', ['write', 'org.macosforge.xquartz.X11', 'enable_iglx', '-bool', 'true'], { env });
      
      // Give XQuartz more time to fully start
      logger.info('Waiting for XQuartz to initialize...');
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  } catch (error) {
    logger.warn('Failed to auto-start XQuartz', error);
  }
}

async function allowXHost(args) {
  try {
    const execa = await getExeca();
    const env = ensurePathEnv(process.env);
    
    // Find xhost
    const fs = require('fs');
    const xhostPaths = ['/opt/X11/bin/xhost', '/usr/X11/bin/xhost', '/usr/bin/xhost'];
    let xhostPath = xhostPaths.find(p => fs.existsSync(p));
    
    if (!xhostPath) {
      logger.warn('xhost not found, skipping X11 access control');
      return;
    }
    
    // Set DISPLAY for xhost
    const xhostEnv = { ...env, DISPLAY: process.env.DISPLAY || ':0' };
    
    for (const arg of args) {
      logger.info(`Running xhost ${arg}`);
      // Add timeout and reject: false to prevent hanging
      await execa(xhostPath, [arg], { 
        env: xhostEnv, 
        reject: false,
        timeout: 5000  // 5 second timeout
      });
    }
  } catch (error) {
    logger.warn('xhost configuration failed (this is usually okay)', error.message);
  }
}

module.exports = {
  buildRuntimeEnv,
  ensureDisplayAccess,
  resetDisplayAccess,
  ensurePathEnv,
  patchProcessPathEnv,
  convertWindowsPathToDockerFormat,
  checkWindowsXServer
};


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
  const nextEnv = { ...env, PATH: updatedValue };
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

  return {
    absoluteProjectDir,
    projectDirName,
    env: ensurePathEnv({
      ...process.env,
      LOCAL_PROJECT_DIR: absoluteProjectDir,
      PROJECT_DIR_NAME: projectDirName,
      DISPLAY: getDisplayEnv(),
      TZ: getTimezone(),
      COMPOSE_PROJECT_NAME: 'ti-toolbox'
    })
  };
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
  patchProcessPathEnv
};


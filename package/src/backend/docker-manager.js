const path = require('path');
const os = require('os');
const { EventEmitter } = require('events');
const Docker = require('dockerode');
const fs = require('fs-extra');
const { logger } = require('./logger');
const { getExeca } = require('./execa');
const { ensurePathEnv } = require('./env');

const MANAGED_CONTAINERS = ['simnibs_container', 'freesurfer_container'];
const FREESURFER_VOLUME = 'ti-toolbox_freesurfer_data';

function toExecEnv(env = {}) {
  return Object.entries(env)
    .filter(([, value]) => typeof value !== 'undefined' && value !== null)
    .map(([key, value]) => `${key}=${value}`);
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

class DockerManager extends EventEmitter {
  constructor(toolboxRoot) {
    super();
    this.toolboxRoot = toolboxRoot;
    this.composeFile = path.join(toolboxRoot, 'docker-compose.yml');
    this.docker = this.createDockerClient();
    this.globalExecEnv = ensurePathEnv(process.env);
    this.stopInFlight = null;
    this.guiRunning = false;
  }

  createDockerClient() {
    if (process.env.DOCKER_HOST) {
      return new Docker(this.parseDockerHost(process.env.DOCKER_HOST));
    }

    if (os.platform() === 'win32') {
      return new Docker({ socketPath: '//./pipe/docker_engine' });
    }

    return new Docker({ socketPath: process.env.DOCKER_SOCK || '/var/run/docker.sock' });
  }

  parseDockerHost(hostValue) {
    if (hostValue.startsWith('npipe://')) {
      return { socketPath: hostValue.replace('npipe:', '') };
    }

    if (hostValue.startsWith('unix://')) {
      return { socketPath: hostValue.replace('unix://', '') };
    }

    if (hostValue.startsWith('tcp://')) {
      const url = new URL(hostValue);
      return {
        host: url.hostname,
        port: Number(url.port || 2375),
        protocol: url.protocol.replace(':', '')
      };
    }

    return {};
  }

  emitProgress(stage, message, meta = {}) {
    const payload = {
      stage,
      message,
      timestamp: new Date().toISOString(),
      ...meta
    };

    logger.info(`[${stage}] ${message}`);
    this.emit('progress', payload);
  }

  async verifyDockerApi() {
    try {
      const versionInfo = await this.docker.version();
      return versionInfo?.Version || 'unknown';
    } catch (error) {
      logger.error('Docker API verification failed:', error);
      logger.info('PATH:', process.env.PATH);
      
      // Try to get more info about Docker availability
      try {
        const { stdout } = await this.exec(['docker', 'version', '--format', '{{.Server.Version}}'], {});
        logger.info('Docker CLI version:', stdout.trim());
      } catch (cliError) {
        logger.error('Docker CLI check also failed:', cliError);
      }
      
      throw new Error(`Docker not accessible. Please ensure Docker Desktop is installed and running. ${error.message}`);
    }
  }

  async verifyComposeCli() {
    const execa = await getExeca();
    const dockerPath = this.findDockerCommand();
    await execa(dockerPath, ['compose', 'version'], { env: this.globalExecEnv });
  }
  
  findDockerCommand() {
    // Try to find docker in common locations
    const fs = require('fs');
    const dockerPaths = [
      '/usr/local/bin/docker',
      '/usr/bin/docker',
      '/opt/homebrew/bin/docker',
      '/Applications/Docker.app/Contents/Resources/bin/docker'
    ];
    
    for (const dockerPath of dockerPaths) {
      if (fs.existsSync(dockerPath)) {
        return dockerPath;
      }
    }
    
    // Fall back to 'docker' command and hope it's in PATH
    return 'docker';
  }

  async pingApi() {
    await this.docker.ping();
  }

  async getExistingContainers() {
    const filters = {
      name: MANAGED_CONTAINERS
    };
    const containers = await this.docker.listContainers({ all: true, filters });
    return containers.map(container => ({
      id: container.Id,
      name: (container.Names && container.Names[0]) ? container.Names[0].replace(/^\//, '') : container.Id,
      state: container.State,
      status: container.Status,
      running: container.State === 'running' || (container.Status || '').includes('Up')
    }));
  }

  async cleanupExistingContainers() {
    const containers = await this.getExistingContainers();
    if (!containers.length) {
      return;
    }

    this.emitProgress('cleanup', 'Stopping existing TI-Toolbox containers…');
    await Promise.all(
      containers.map(async containerInfo => {
        try {
          const container = this.docker.getContainer(containerInfo.id);
          if (containerInfo.running) {
            await container.stop({ t: 10 });
          }
          await container.remove({ force: true });
        } catch (error) {
          logger.warn(`Failed to clean container ${containerInfo.name}`, error);
        }
      })
    );
  }

  async ensureVolume() {
    this.emitProgress('volume', 'Ensuring Freesurfer data volume exists…');
    try {
      await this.docker.createVolume({ Name: FREESURFER_VOLUME });
    } catch (error) {
      if (error.statusCode !== 409) {
        throw error;
      }
    }
  }

  async composeUp(env) {
    this.emitProgress('compose-up', 'Starting Docker Compose services…');
    const execa = await getExeca();
    const execEnv = ensurePathEnv(env);
    const dockerPath = this.findDockerCommand();
    await execa(dockerPath, ['compose', '-f', this.composeFile, 'up', '--build', '-d'], {
      env: execEnv,
      cwd: this.toolboxRoot,
      timeout: 180000
    });
  }

  async composeDown(env) {
    const composeExists = await fs.pathExists(this.composeFile);
    if (!composeExists) {
      return;
    }

    const execa = await getExeca();
    const execEnv = ensurePathEnv(env);
    const dockerPath = this.findDockerCommand();
    await execa(dockerPath, ['compose', '-f', this.composeFile, 'down', '--remove-orphans'], {
      env: execEnv,
      cwd: this.toolboxRoot,
      timeout: 60000,
      reject: false
    });
  }

  async waitForContainer(containerName, timeoutMs = 120000) {
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
      const list = await this.docker.listContainers({ all: true, filters: { name: [containerName] } });
      if (list.some(container => container.State === 'running' || (container.Status || '').includes('Up'))) {
        return;
      }

      await delay(2000);
    }

    throw new Error(`${containerName} is not running after ${timeoutMs / 1000}s.`);
  }

  async prepareStack(env) {
    const composeExists = await fs.pathExists(this.composeFile);
    if (!composeExists) {
      throw new Error(`docker-compose.yml not found at ${this.composeFile}`);
    }

    this.emitProgress('preflight', 'Validating Docker installation…');
    await this.verifyDockerApi();
    await this.verifyComposeCli();
    await this.pingApi();

    this.emitProgress('cleanup', 'Cleaning up stale containers…');
    await this.cleanupExistingContainers();
    await this.ensureVolume();
    await this.composeUp(env);
    await this.waitForContainer('simnibs_container');
  }

  async launchGui(env) {
    this.emitProgress('gui', 'Launching TI-Toolbox GUI inside simnibs_container…');
    const container = this.docker.getContainer('simnibs_container');
    
    // Log environment for debugging
    logger.info('GUI Environment:', {
      DISPLAY: env.DISPLAY,
      LOCAL_PROJECT_DIR: env.LOCAL_PROJECT_DIR,
      PROJECT_DIR_NAME: env.PROJECT_DIR_NAME,
      TZ: env.TZ
    });
    
    const execEnv = toExecEnv({
      DISPLAY: env.DISPLAY,
      LOCAL_PROJECT_DIR: env.LOCAL_PROJECT_DIR,
      PROJECT_DIR_NAME: env.PROJECT_DIR_NAME,
      TZ: env.TZ
    });

    const exec = await container.exec({
      Cmd: ['bash', '/ti-toolbox/ti-toolbox/cli/GUI.sh'],
      AttachStdout: true,
      AttachStderr: true,
      AttachStdin: false,
      Tty: true,
      WorkingDir: '/ti-toolbox',
      Env: execEnv
    });

    const stream = await exec.start({ hijack: true, stdin: false });
    this.guiRunning = true;

    stream.on('data', chunk => {
      const message = chunk.toString();
      logger.info('[GUI Output]', message);
      this.emit('log', message);
    });

    stream.on('end', async () => {
      this.guiRunning = false;
      this.emitProgress('gui-exited', 'TI-Toolbox GUI closed. Cleaning up containers…');
      await this.stop(env);
      this.emit('gui-exited');
    });

    stream.on('error', async (error) => {
      this.guiRunning = false;
      logger.error('GUI stream error', error);
      await this.stop(env);
      this.emit('gui-error', error);
    });

    this.emitProgress('gui-started', 'TI-Toolbox GUI launched successfully.');
    return exec.id;
  }

  async stop(env) {
    if (this.stopInFlight) {
      return this.stopInFlight;
    }

    this.stopInFlight = (async () => {
      this.emitProgress('shutdown', 'Stopping Docker services…');
      const execEnv = ensurePathEnv(env || process.env);
      await this.composeDown(execEnv);
      await this.cleanupExistingContainers();
      this.guiRunning = false;
      this.stopInFlight = null;
      this.emitProgress('shutdown-complete', 'All Docker services stopped successfully');
    })();

    return this.stopInFlight;
  }
}

module.exports = DockerManager;


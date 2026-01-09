const path = require('path');
const fs = require('fs-extra');
const { logger } = require('./logger');

const REQUIRED_DIRS = [
  ['code', 'ti-toolbox', 'config'],
  ['derivatives', 'ti-toolbox', '.ti-toolbox-info'],
  ['derivatives', 'freesurfer'],
  ['derivatives', 'SimNIBS'],
  ['sourcedata']
];

async function validateProjectDirectory(projectDir) {
  if (!projectDir) {
    throw new Error('Project directory is required.');
  }

  try {
    const stats = await fs.stat(projectDir);
    if (!stats.isDirectory()) {
      throw new Error('Selected path is not a directory.');
    }
  } catch (error) {
    if (error.code === 'ENOENT') {
      throw new Error(`Project directory does not exist: ${projectDir}`);
    }
    throw error;
  }

  try {
    await fs.access(projectDir, fs.constants.R_OK | fs.constants.W_OK);
  } catch (error) {
    throw new Error(`Cannot read/write to project directory: ${projectDir}. Please check permissions.`);
  }

  return path.resolve(projectDir);
}

async function initializeProject(projectDir) {
  const configDir = path.join(projectDir, 'code', 'tit', 'config');
  const initializedMarker = path.join(configDir, '.initialized');

  try {
    if (await fs.pathExists(initializedMarker)) {
      logger.info(`Project already initialized: ${projectDir}`);
      return { created: false };
    }
  } catch (error) {
    logger.warn(`Could not check initialization marker: ${error.message}`);
  }

  try {
    await Promise.all(
      REQUIRED_DIRS.map(async (segments) => {
        const dir = path.join(projectDir, ...segments);
        try {
          await fs.ensureDir(dir);
          logger.info(`Created directory: ${dir}`);
        } catch (dirError) {
          logger.error(`Failed to create directory ${dir}: ${dirError.message}`);
          throw dirError;
        }
      })
    );

    await fs.ensureFile(initializedMarker);
    logger.info(`Project initialized successfully: ${projectDir}`);
    return { created: true };
  } catch (error) {
    logger.error(`Failed to initialize project: ${error.message}`);
    throw new Error(`Failed to initialize project structure: ${error.message}`);
  }
}

module.exports = {
  validateProjectDirectory,
  initializeProject
};

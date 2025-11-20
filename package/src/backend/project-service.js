const path = require('path');
const fs = require('fs-extra');

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

  const stats = await fs.stat(projectDir);
  if (!stats.isDirectory()) {
    throw new Error('Selected path is not a directory.');
  }

  await fs.access(projectDir, fs.constants.R_OK | fs.constants.W_OK);
  return path.resolve(projectDir);
}

async function initializeProject(projectDir) {
  const configDir = path.join(projectDir, 'code', 'ti-toolbox', 'config');
  const initializedMarker = path.join(configDir, '.initialized');

  if (await fs.pathExists(initializedMarker)) {
    return { created: false };
  }

  await Promise.all(
    REQUIRED_DIRS.map(async segments => {
      const dir = path.join(projectDir, ...segments);
      await fs.ensureDir(dir);
    })
  );

  await fs.ensureFile(initializedMarker);
  return { created: true };
}

module.exports = {
  validateProjectDirectory,
  initializeProject
};


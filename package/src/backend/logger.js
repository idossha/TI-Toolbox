const path = require('path');
const electronLog = require('electron-log');

let isConfigured = false;

function configureLogger(app) {
  if (isConfigured) {
    return electronLog;
  }

  // Align console/file levels for consistent diagnostics
  electronLog.transports.console.level = 'info';
  electronLog.transports.file.level = 'info';
  electronLog.transports.file.maxSize = 10 * 1024 * 1024; // 10 MB

  if (app) {
    const logPath = path.join(app.getPath('logs'), 'ti-toolbox.log');
    electronLog.transports.file.resolvePathFn = () => logPath;
  }

  electronLog.catchErrors({
    showDialog: false
  });

  isConfigured = true;
  return electronLog;
}

module.exports = {
  configureLogger,
  logger: electronLog
};


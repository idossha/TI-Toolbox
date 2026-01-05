const { ipcRenderer } = require('electron');

const projectPathInput = document.getElementById('project-path');
const browseBtn = document.getElementById('browse-btn');
const newProjectBtn = document.getElementById('new-project-btn');
const launchBtn = document.getElementById('launch-btn');
const launchText = document.getElementById('launch-text');
const launchSpinner = document.getElementById('launch-spinner');
const statusMessage = document.getElementById('status-message');
const dockerStatus = document.getElementById('docker-status');
const dockerStatusText = document.getElementById('docker-status-text');
const xserverStatus = document.getElementById('xserver-status');
const progressInfo = document.getElementById('progress-info');
const progressText = document.getElementById('progress-text');
const stopBtn = document.getElementById('stop-btn');
const logPathEl = document.getElementById('log-path');
const openLogsBtn = document.getElementById('open-logs-btn');
const activityList = document.getElementById('activity-list');
const clearActivityBtn = document.getElementById('clear-activity-btn');

let isLaunching = false;
let sessionActive = false;

function showStatus(message, type = 'info') {
  statusMessage.textContent = message;
  statusMessage.className = `status-message ${type}`;
  statusMessage.classList.remove('hidden');
}

function hideStatus() {
  statusMessage.classList.add('hidden');
}

function showProgress(text) {
  progressText.textContent = text;
  progressInfo.classList.remove('hidden');
}

function hideProgress() {
  progressInfo.classList.add('hidden');
}

function isProjectDirValid(value) {
  return Boolean(value && value.trim().length > 0);
}

function refreshLaunchButton() {
  const validPath = isProjectDirValid(projectPathInput.value);
  const disabled = !validPath || isLaunching || sessionActive;
  launchBtn.disabled = disabled;
}

function setLaunchingState(launching) {
  isLaunching = launching;
  if (launching) {
    launchText.textContent = 'Launching...';
    launchSpinner.classList.remove('hidden');
  } else {
    launchText.textContent = 'Launch TI-Toolbox';
    launchSpinner.classList.add('hidden');
  }
  refreshLaunchButton();
}


async function checkXServer() {
  const platform = await ipcRenderer.invoke('get-platform');

  if (platform !== 'win32') {
    xserverStatus.classList.add('hidden');
    return true;
  }

  // Always perform the check dynamically on Windows
  const result = await ipcRenderer.invoke('check-xserver');

  if (result.available) {
    xserverStatus.classList.add('hidden');
    return true;
  }

  // Show warning if X server is not available
  xserverStatus.classList.remove('hidden');
  return false;
}

async function checkDocker() {
  dockerStatus.classList.remove('hidden');
  dockerStatusText.textContent = 'Checking...';

  const result = await ipcRenderer.invoke('check-docker');

  if (result.available) {
    let statusText = '✓ Docker is running';

    if (result.existingContainers?.length) {
      const runningContainers = result.existingContainers.filter(c => c.running);
      if (runningContainers.length > 0) {
        statusText += ` (${runningContainers.length} container(s) running)`;
        dockerStatusText.style.color = '#ffc107';
        showStatus('TI-Toolbox containers are already running. They will be restarted.', 'info');
        // Show stop button if containers are running
        stopBtn.classList.remove('hidden');
        stopBtn.disabled = false;
      } else {
        statusText += ` (${result.existingContainers.length} container(s) stopped)`;
        dockerStatusText.style.color = '#28a745';
      }
    } else {
      dockerStatusText.style.color = '#28a745';
    }

    dockerStatusText.textContent = statusText;
    return true;
  }

  dockerStatusText.textContent = `✗ ${result.error}`;
  dockerStatusText.style.color = '#dc3545';
  showStatus(result.error, 'error');
  return false;
}

async function loadSavedPath() {
  const savedPath = await ipcRenderer.invoke('get-saved-path');
  if (savedPath) {
    projectPathInput.value = savedPath;
  }
  refreshLaunchButton();
}

function appendActivity({ stage, message, timestamp }) {
  const item = document.createElement('li');

  // Format timestamp to HH:MM:SS
  const time = new Date(timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  // Terminal-style output with time format: |time| message|
  item.textContent = `|${time}| ${message}`;

  // Add styling based on stage or message content
  if (stage === 'gui-started' || stage === 'shutdown-complete' || message.includes('successfully') || message.includes('✓')) {
    item.classList.add('success');
  } else if (stage === 'error' || message.includes('error') || message.includes('failed') || message.includes('✗')) {
    item.classList.add('error');
  } else if (stage === 'warning' || message.includes('warning') || message.includes('⚠')) {
    item.classList.add('warning');
  }

  activityList.appendChild(item);

  // Keep more lines for terminal-like scrolling
  while (activityList.children.length > 100) {
    activityList.removeChild(activityList.firstChild);
  }

  // Auto-scroll to bottom
  activityList.scrollTop = activityList.scrollHeight;
}

async function hydrateLogPath() {
  const logPath = await ipcRenderer.invoke('get-log-path');
  if (logPath) {
    logPathEl.textContent = logPath;
    openLogsBtn.disabled = false;
  } else {
    logPathEl.textContent = 'Unavailable';
    openLogsBtn.disabled = true;
  }
}

browseBtn.addEventListener('click', async () => {
  const selected = await ipcRenderer.invoke('select-directory');
  if (selected) {
    projectPathInput.value = selected;
    refreshLaunchButton();
    hideStatus();
  }
});

newProjectBtn.addEventListener('click', async () => {
  // Show dialog to select where to create the new project
  const selected = await ipcRenderer.invoke('select-directory');
  if (!selected) {
    return;
  }

  // Ask if user wants example data
  const includeExampleData = await showExampleDataDialog();
  
  showProgress('Creating new project...');
  
  try {
    const result = await ipcRenderer.invoke('create-new-project', selected, includeExampleData);
    
    if (result.success) {
      projectPathInput.value = result.projectDir;
      refreshLaunchButton();
      
      let message = 'New project created successfully!';
      if (result.exampleDataCopied) {
        message += ' Example data (sub-ernie and sub-MNI152) has been copied to your project.';
      }
      
      showStatus(message, 'success');
      appendActivity({ 
        stage: 'project', 
        message: 'Created new project with BIDS structure', 
        timestamp: new Date().toISOString() 
      });
    } else {
      throw new Error(result.error);
    }
  } catch (error) {
    showStatus(`Failed to create project: ${error.message}`, 'error');
  } finally {
    hideProgress();
  }
});

function showExampleDataDialog() {
  return new Promise((resolve) => {
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    `;
    
    // Create dialog box
    const dialogBox = document.createElement('div');
    dialogBox.style.cssText = `
      background: white;
      border-radius: 12px;
      padding: 30px;
      max-width: 500px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    `;
    
    dialogBox.innerHTML = `
      <h2 style="margin: 0 0 15px 0; color: #333; font-size: 22px;">Include Example Data?</h2>
      <p style="margin: 0 0 20px 0; color: #666; line-height: 1.6;">
        Would you like to include example data (sub-ernie and sub-MNI152) in your new project?
        <br><br>
        This is recommended for first-time users to explore the toolbox functionality.
      </p>
      <div style="display: flex; gap: 10px; justify-content: flex-end;">
        <button id="dialog-no" class="btn btn-secondary" style="min-width: 100px;">No, Skip</button>
        <button id="dialog-yes" class="btn btn-primary" style="min-width: 100px;">Yes, Include</button>
      </div>
    `;
    
    overlay.appendChild(dialogBox);
    document.body.appendChild(overlay);
    
    // Handle button clicks
    document.getElementById('dialog-yes').addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(true);
    });
    
    document.getElementById('dialog-no').addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(false);
    });
    
    // Handle clicking outside the dialog
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        document.body.removeChild(overlay);
        resolve(false);
      }
    });
  });
}

projectPathInput.addEventListener('input', () => {
  refreshLaunchButton();
});

launchBtn.addEventListener('click', async () => {
  if (isLaunching || sessionActive) {
    return;
  }

  const projectDir = projectPathInput.value.trim();
  if (!isProjectDirValid(projectDir)) {
    showStatus('Please select a project directory first.', 'error');
    return;
  }

  // Check X server on Windows before proceeding
  const xserverOk = await checkXServer();
  if (!xserverOk) {
    showStatus('X server not detected. Please ensure VcXsrv or another X server is running on Windows.', 'error');
    return;
  }

  const dockerOk = await checkDocker();
  if (!dockerOk) {
    return;
  }

  hideStatus();
  showProgress('Preparing TI-Toolbox…');
  setLaunchingState(true);

  try {
    const result = await ipcRenderer.invoke('start-toolbox', projectDir);
    if (result.success) {
      if (result.isNewProject) {
        appendActivity({ stage: 'project', message: 'Initialized new project structure.', timestamp: new Date().toISOString() });
      }

      showProgress('Docker stack is starting…');
    } else {
      throw new Error(result.error);
    }
  } catch (error) {
    showStatus(`Failed to launch: ${error.message}`, 'error');
    hideProgress();
  } finally {
    setLaunchingState(false);
  }
});

stopBtn.addEventListener('click', async () => {
  stopBtn.disabled = true;
  showProgress('Stopping TI-Toolbox containers and GUI…');
  const result = await ipcRenderer.invoke('stop-toolbox');
  if (result.success) {
    showStatus('Successfully stopped all TI-Toolbox containers.', 'success');
    stopBtn.classList.add('hidden');
    sessionActive = false;
    refreshLaunchButton();
    // Check Docker status again to update the display
    setTimeout(() => checkDocker(), 1000);
  } else {
    showStatus(result.error || 'Failed to stop containers.', 'error');
    stopBtn.disabled = false;
  }
  hideProgress();
});

openLogsBtn.addEventListener('click', async () => {
  await ipcRenderer.invoke('reveal-log-file');
});

clearActivityBtn.addEventListener('click', () => {
  activityList.innerHTML = '';
});

ipcRenderer.on('launcher-progress', (_event, payload) => {
  appendActivity(payload);
  showProgress(payload.message);

  if (payload.stage === 'gui-started') {
    sessionActive = true;
    stopBtn.classList.remove('hidden');
    stopBtn.disabled = false;
    showStatus('TI-Toolbox GUI is running. You can minimize this window.', 'success');
  }

  if (payload.stage === 'gui-exited') {
    sessionActive = false;
    stopBtn.classList.add('hidden');
    stopBtn.disabled = true;
    hideProgress();
    showStatus('TI-Toolbox session finished. You can start another session.', 'info');
  }

  if (payload.stage === 'shutdown-complete') {
    hideProgress();
    showStatus('All Docker services stopped successfully.', 'success');
  }

  refreshLaunchButton();
});

ipcRenderer.on('launcher-log', (_event, payload) => {
  if (!payload?.message) {
    return;
  }

  // Filter out specific libGL error messages
  const message = payload.message.trim();
  if (message.includes('libGL error: No matching fbConfigs or visuals found') ||
      message.includes('libGL error: failed to load driver: swrast')) {
    return;
  }

  appendActivity({
    stage: 'log',
    message: message,
    timestamp: payload.timestamp || new Date().toISOString()
  });
});

(async () => {
  await loadSavedPath();
  await checkXServer();
  await checkDocker();
  await hydrateLogPath();
})();

// Re-check X server on Windows when window regains focus
window.addEventListener('focus', async () => {
  const platform = await ipcRenderer.invoke('get-platform');
  if (platform === 'win32') {
    await checkXServer();
  }
});

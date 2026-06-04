const { app, BrowserWindow, Tray, Menu, nativeImage, dialog } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const http = require('http');

const BACKEND_URL = 'http://localhost:8780';
const HEALTH_URL = `${BACKEND_URL}/health`;
const SHUTDOWN_URL = `${BACKEND_URL}/shutdown`;
const PID_FILE = path.join(os.homedir(), '.deep6', 'gexdoctor_v2.pid');
const WINDOW_WIDTH = 800;
const WINDOW_HEIGHT = 800;
const MAX_HEALTH_ATTEMPTS = 30;

let mainWindow = null;
let tray = null;
let alwaysOnTop = false;
let backendProcess = null;
let backendPid = null;
let bridgeProcess = null;
let bridgePid = null;
let healthCheckInterval = null;
let healthCheckAttempts = 0;

function clearHealthCheckInterval() {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval);
    healthCheckInterval = null;
  }
}

function getProjectRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }

  return path.join(__dirname, '..', '..');
}

function isProcessAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function cleanupStalePidFile(pid) {
  try {
    if (fs.existsSync(PID_FILE)) {
      const filePid = parseInt(fs.readFileSync(PID_FILE, 'utf8').trim(), 10);
      if (!Number.isNaN(filePid) && filePid === pid) {
        fs.unlinkSync(PID_FILE);
      }
    }
  } catch {
    // Ignore PID file cleanup failures.
  }
}

function postShutdown() {
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 8780,
        path: '/shutdown',
        method: 'POST',
      },
      (res) => {
        res.resume();
        resolve();
      }
    );

    req.on('error', resolve);
    req.setTimeout(2000, () => {
      req.destroy();
      resolve();
    });
    req.end();
  });
}

function spawnBackend() {
  const root = getProjectRoot();

  try {
    if (fs.existsSync(PID_FILE)) {
      const existingPid = parseInt(fs.readFileSync(PID_FILE, 'utf8').trim(), 10);
      if (!Number.isNaN(existingPid) && isProcessAlive(existingPid)) {
        backendPid = existingPid;
        console.log(`[GEX] Reusing existing backend PID: ${existingPid}`);
        return;
      }

      fs.unlinkSync(PID_FILE);
    }
  } catch {
    // Ignore PID file read/cleanup errors and try a fresh spawn.
  }

  console.log('[GEX] Spawning Python backend...');

  const command = app.isPackaged
    ? path.join(root, 'gex_terminal_backend', 'gex_terminal_backend.exe')
    : 'python';
  const args = app.isPackaged ? [] : ['-m', 'gex_terminal'];

  backendProcess = spawn(command, args, {
    cwd: root,
    windowsHide: true,
    detached: false,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  backendPid = backendProcess.pid ?? null;
  console.log(`[GEX] Backend PID: ${backendPid ?? 'unknown'}`);

  backendProcess.stdout.on('data', (data) => {
    process.stdout.write(`[backend] ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    process.stderr.write(`[backend:err] ${data}`);
  });

  backendProcess.on('error', (error) => {
    console.error('[GEX] Backend spawn failed:', error);
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`[GEX] Backend exited with code: ${code ?? 'null'}, signal: ${signal ?? 'null'}`);
    if (backendPid) {
      cleanupStalePidFile(backendPid);
    }
    backendProcess = null;
    backendPid = null;
  });
}

function spawnNT8Bridge() {
  const root = getProjectRoot();
  const bridgeScript = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'scripts', 'gex_terminal_nt8_bridge.py')
    : path.join(root, 'scripts', 'gex_terminal_nt8_bridge.py');

  if (!require('fs').existsSync(bridgeScript)) {
    console.log('[bridge] Script not found, skipping NT8 bridge');
    return;
  }

  console.log('[bridge] Spawning NT8 bridge...');
  bridgeProcess = spawn('python', [bridgeScript], {
    cwd: root,
    windowsHide: true,
    detached: false,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  bridgePid = bridgeProcess.pid;
  console.log(`[bridge] NT8 Bridge PID: ${bridgePid}`);

  bridgeProcess.stdout.on('data', (d) => process.stdout.write(`[bridge] ${d}`));
  bridgeProcess.stderr.on('data', (d) => process.stderr.write(`[bridge:err] ${d}`));

  bridgeProcess.on('exit', (code) => {
    console.log(`[bridge] NT8 Bridge exited with code: ${code}`);
    bridgeProcess = null;
    bridgePid = null;

    // Auto-restart after 5 seconds if app is still running
    if (!app.isQuiting && !app._isShuttingDown) {
      console.log('[bridge] Will auto-restart NT8 bridge in 5s...');
      setTimeout(() => {
        if (!app.isQuiting && !app._isShuttingDown) {
          console.log('[bridge] Auto-restarting NT8 bridge...');
          spawnNT8Bridge();
        }
      }, 5000);
    }
  });
}

function pollHealth() {
  clearHealthCheckInterval();
  healthCheckAttempts = 0;

  healthCheckInterval = setInterval(() => {
    healthCheckAttempts += 1;

    if (healthCheckAttempts > MAX_HEALTH_ATTEMPTS) {
      clearHealthCheckInterval();
      dialog.showErrorBox(
        'GEX Doctor — Backend Failed',
        `Python backend did not start within 15 seconds.\n\nCheck that Python is installed and try again.\n\nPID: ${backendPid ?? 'unknown'}`
      );
      app.quit();
      return;
    }

    const req = http.get(HEALTH_URL, (res) => {
      res.resume();
      if (res.statusCode === 200) {
        clearHealthCheckInterval();
        console.log('[GEX] Backend healthy — loading UI');
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.loadURL(BACKEND_URL);
          spawnNT8Bridge();
        }
      }
    });

    req.on('error', () => {
      // Backend not ready yet.
    });

    req.setTimeout(400, () => {
      req.destroy();
    });
  }, 500);
}

async function shutdownBackend() {
  clearHealthCheckInterval();

  // Also kill NT8 bridge if running
  if (bridgePid) {
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /PID ${bridgePid} /T /F`, { stdio: 'ignore' });
      } else {
        process.kill(-bridgePid, 'SIGKILL');
      }
    } catch { /* already dead */ }
    bridgePid = null;
  }

  if (!backendPid) {
    return;
  }

  const pidToKill = backendPid;

  await postShutdown();

  await new Promise((resolve) => {
    setTimeout(() => {
      if (!isProcessAlive(pidToKill)) {
        cleanupStalePidFile(pidToKill);
        resolve();
        return;
      }

      try {
        if (process.platform === 'win32') {
          execSync(`taskkill /PID ${pidToKill} /T /F`, { stdio: 'ignore' });
        } else {
          process.kill(pidToKill, 'SIGKILL');
        }
      } catch {
        // Process may already be gone.
      }

      cleanupStalePidFile(pidToKill);
      resolve();
    }, 3000);
  });
}

function updateTrayMenu() {
  if (!tray) return;

  const menu = Menu.buildFromTemplate([
    {
      label: mainWindow && mainWindow.isVisible() ? 'Hide GEX Doctor' : 'Show GEX Doctor',
      click: () => {
        if (!mainWindow) return;

        if (mainWindow.isVisible()) {
          mainWindow.hide();
        } else {
          mainWindow.show();
          mainWindow.focus();
        }

        updateTrayMenu();
      },
    },
    {
      label: 'Always on Top',
      type: 'checkbox',
      checked: alwaysOnTop,
      click: (item) => {
        alwaysOnTop = item.checked;
        if (mainWindow) mainWindow.setAlwaysOnTop(alwaysOnTop);
        updateTrayMenu();
      },
    },
    { type: 'separator' },
    {
      label: 'Quit GEX Doctor',
      click: () => {
        app.isQuiting = true;
        tray = null;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(menu);
}

function createTray() {
  const trayIconPath = path.join(__dirname, 'assets', 'tray.png');
  const trayIcon = nativeImage.createFromPath(trayIconPath);

  tray = new Tray(trayIcon);
  tray.setToolTip('GEX Doctor v2.0');

  updateTrayMenu();

  tray.on('click', () => {
    if (!mainWindow) return;

    if (mainWindow.isVisible() && mainWindow.isFocused()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }

    updateTrayMenu();
  });
}

function createWindow() {
  const iconPath = path.join(__dirname, 'assets', 'icon.png');

  mainWindow = new BrowserWindow({
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    resizable: false,
    title: 'GEX Doctor v2.0',
    backgroundColor: '#0D0D0D',
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Load the loading screen first
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));

  // Hide to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!app.isQuiting) {
      event.preventDefault();
      mainWindow.hide();
      updateTrayMenu();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();
  createTray();
  spawnBackend();
  pollHealth();
});

app.on('window-all-closed', () => {
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  } else if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    updateTrayMenu();
  }
});

app.on('before-quit', async (event) => {
  if (!app._isShuttingDown) {
    event.preventDefault();
    app._isShuttingDown = true;
    app.isQuiting = true;
    await shutdownBackend();
    app.quit();
  }
});

module.exports = { mainWindow: () => mainWindow, BACKEND_URL };

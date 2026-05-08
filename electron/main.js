const {
  app, BrowserWindow, ipcMain, Tray, Menu,
  nativeImage, dialog, shell,
} = require('electron')
const path  = require('path')
const fs    = require('fs')
const { spawn } = require('child_process')

let win, tray, pythonProcess, isQuitting = false

// ── Quarantine helper ─────────────────────────────────────────────────────────
// Ad hoc signed / zip-distributed builds are quarantined by macOS Gatekeeper.
// Call this on the app bundle itself at startup and on any freshly-extracted
// update bundle before relaunching — otherwise Electron helpers and the Python
// backend will be blocked by Gatekeeper at runtime.
function clearQuarantine (targetPath) {
  if (process.platform !== 'darwin') return
  try {
    require('child_process').execSync(`xattr -cr "${targetPath}"`, { stdio: 'ignore' })
    console.log(`[xattr] Cleared quarantine: ${targetPath}`)
  } catch (e) {
    console.warn('[xattr] Failed to clear quarantine:', e.message)
  }
}

// Derive the .app bundle root from the running executable path.
// e.g. …/OpenProxy.app/Contents/MacOS/OpenProxy → …/OpenProxy.app
function getAppBundlePath () {
  const exe = app.getPath('exe')
  const idx = exe.indexOf('.app/')
  return idx !== -1 ? exe.slice(0, idx + 4) : null
}

let bustCacheEnabled = false
let macosProxyActive = false
let currentTheme = 'dark'
let toolbarVisibility = {
  vpnMode: true, breakpoints: true, mapLocal: true,
  mapRemote: true, highlights: true, scripts: false,
  certificates: true, throttle: true, bustCache: true,
  osProxy: true,
}

// Windows titleBarOverlay colors per theme (bg = --bg-sidebar, symbol = --fg-muted)
const OVERLAY_COLORS = {
  dark:     { color: '#222223', symbolColor: '#8b949e' },
  midnight: { color: '#161b22', symbolColor: '#8b949e' },
  ocean:    { color: '#132540', symbolColor: '#7da8c8' },
  crimson:  { color: '#200f13', symbolColor: '#a07080' },
  ember:    { color: '#e8e8e8', symbolColor: '#5c5c5c' },
  light:    { color: '#f0f0f0', symbolColor: '#666666' },
}

async function buildUI () {
  if (app.isPackaged) return

  return new Promise((resolve) => {
    console.log('[UI] Building...')
    const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'

    const proc = spawn(npm, ['run', 'build'], {
      cwd: path.join(__dirname, '..', 'ui'),
      stdio: 'inherit',
      shell: true,
    })

    proc.on('close', code => {
      if (code !== 0) console.warn('[UI] Build exited with code', code)
      else console.log('[UI] Build complete')
      resolve()
    })

    proc.on('error', err => {
      console.error('[UI] Build failed:', err)
      resolve()
    })
  })
}

// ── Python backend ────────────────────────────────────────────────────────────
function startPython () {
  return new Promise((resolve) => {
    let exe, args, cwd

    if (app.isPackaged) {
      // --onedir layout: backend/OpenProxy-server/OpenProxy-server(.exe)
      const bin = process.platform === 'win32' ? 'OpenProxy-server.exe' : 'OpenProxy-server'
      exe  = path.join(process.resourcesPath, 'backend', 'OpenProxy-server', bin)
      args = []
      cwd  = process.resourcesPath
    } else {
      const pyBin   = process.platform === 'win32' ? 'python.exe' : 'python3'
      const venvDir = process.platform === 'win32' ? 'Scripts' : 'bin'
      exe  = path.join(__dirname, '..', 'venv', venvDir, pyBin)
      args = [path.join(__dirname, '..', 'main.py')]
      cwd  = path.join(__dirname, '..')
    }

    console.log(`[Python] ${exe} ${args.join(' ')}`)
    pythonProcess = spawn(exe, args, { cwd })

    // Resolve once Python prints its startup line — the WS server is ready
    const timeout = setTimeout(() => {
      console.warn('[Python] ready timeout — loading UI anyway')
      resolve()
    }, 15000)

    pythonProcess.stdout.on('data', d => {
      process.stdout.write(`[py] ${d}`)
      if (d.toString().includes('Starting OpenProxy')) {
        clearTimeout(timeout)
        resolve()
      }
    })
    pythonProcess.stderr.on('data', d => process.stderr.write(`[py] ${d}`))
    pythonProcess.on('exit', code => console.log(`[Python] exit ${code}`))
  })
}

// ── BrowserWindow ────────────────────────────────────────────────────────────
function createWindow () {
  win = new BrowserWindow({
    width:    1280,
    height:   800,
    minWidth: 1024,
    minHeight: 720,
    // macOS: traffic lights overlay the content (hiddenInset)
    // Windows: title bar hidden, native controls added via titleBarOverlay
    // Linux: title bar hidden, custom controls drawn in TitleBar.vue
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    // Windows-only native overlay controls (macOS uses hiddenInset, Linux uses custom HTML buttons)
    ...(process.platform === 'win32' && {
      titleBarOverlay: {
        color:       '#222223',
        symbolColor: '#8b949e',
        height:      30,
      },
    }),
    backgroundColor: '#222223',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.on('close', e => {
    if (!isQuitting) {
      e.preventDefault()
      win.hide()
    }
  })

  const sendMaximized = () => win?.webContents.send('window:maximized', win.isMaximized())
  win.on('maximize',   sendMaximized)
  win.on('unmaximize', sendMaximized)
}

// ── IPC ──────────────────────────────────────────────────────────────────────
function setupIPC () {
  ipcMain.on('window:minimize',        () => win?.minimize())
  ipcMain.on('window:toggleFullscreen', () => win?.setFullScreen(!win.isFullScreen()))
  ipcMain.on('window:close',           () => win?.hide())
  ipcMain.on('window:quit',            () => quitApp())
  ipcMain.on('window:zoom', () => {
    if (!win) return
    // On macOS maximize() calls NSWindow performZoom which is a native toggle
    if (process.platform === 'darwin') {
      win.maximize()
    } else {
      win.isMaximized() ? win.unmaximize() : win.maximize()
    }
  })
  ipcMain.on('shell:openExternal', (_e, url) => shell.openExternal(url))
  ipcMain.on('menu:bustCacheSync', (_e, val) => {
    bustCacheEnabled = !!val
    setupMenu()
  })

  ipcMain.on('menu:macosProxySync', (_e, val) => {
    macosProxyActive = !!val
    setupMenu()
  })

  ipcMain.on('theme:changed', (_e, id) => {
    currentTheme = id
    if (process.platform === 'win32' && win) {
      const colors = OVERLAY_COLORS[id] || OVERLAY_COLORS.dark
      win.setTitleBarOverlay({ ...colors, height: 38 })
    }
    setupMenu()
  })

  ipcMain.on('toolbar:syncToMain', (_e, vis) => {
    toolbarVisibility = { ...toolbarVisibility, ...vis }
    setupMenu()
  })

  ipcMain.handle('dialog:saveFile', async (_e, { filename, content }) => {
    const { filePath, canceled } = await dialog.showSaveDialog(win, {
      defaultPath: path.join(app.getPath('desktop'), filename),
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!canceled && filePath) fs.writeFileSync(filePath, content, 'utf8')
  })

  ipcMain.handle('dialog:selectFile', async (_e, opts = {}) => {
    const { canceled, filePaths } = await dialog.showOpenDialog(win, {
      title:      opts.title || 'Select File',
      properties: ['openFile'],
      filters:    opts.filters || [
        { name: 'All Files', extensions: ['*'] },
        { name: 'JSON',      extensions: ['json'] },
        { name: 'Images',    extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'] },
        { name: 'Text',      extensions: ['txt', 'html', 'xml', 'csv'] },
      ],
    })
    return canceled ? null : filePaths[0]
  })

  // Updater calls this with the path of the freshly-extracted .app before
  // relaunching, so Gatekeeper doesn't block the new bundle on macOS.
  ipcMain.on('update:clearQuarantine', (_e, newAppPath) => {
    clearQuarantine(newAppPath)
  })

  ipcMain.on('app:getVersion', (e) => { e.returnValue = app.getVersion() })
}

// ── Tray ─────────────────────────────────────────────────────────────────────
function setupTray () {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.png')
    : path.join(__dirname, '..', 'icon.png')

  let img = nativeImage.createFromPath(iconPath)

  // Fallback: if icon not found, create a plain coloured image
  if (img.isEmpty()) {
    img = nativeImage.createFromDataURL(
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmJLR0QA/wD/AP+gvaeTAAAAMElEQVQ4jWNgGAWDHfwnIJ6hAT8YGBj+E6MZBaMGjBowasCoAaMGjBowGAEAAAD//wMABdsC9QplbtIAAAAASUVORK5CYII='
    )
  }

  if (process.platform === 'darwin') img = img.resize({ width: 16, height: 16 })

  try {
    tray = new Tray(img)
    tray.setToolTip('OpenProxy')
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Open OpenProxy', click: showWindow },
      { type: 'separator' },
      { label: 'Quit', click: () => quitApp() },
    ]))
    tray.on('click', showWindow)
  } catch (err) {
    console.error('[Tray] Failed to create tray icon:', err)
  }
}

// ── App menu ─────────────────────────────────────────────────────────────────
function setupMenu () {
  const js = code =>
    win?.webContents.executeJavaScript(`window.__op && window.__op.${code}`)

  const template = [
    ...(process.platform === 'darwin' ? [{ role: 'appMenu' }] : []),
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'Proxy',
      submenu: [
        { label: 'Record / Pause',  click: () => js('toggleRecording()') },
        { label: 'Compose Request', click: () => js('openComposeNew()') },
        { label: 'Clear Traffic',   click: () => js('clearTraffic()') },
        { type: 'separator' },
        ...(process.platform === 'darwin' ? [{
          label:   'OS Proxy',
          type:    'checkbox',
          checked: macosProxyActive,
          click:   () => js('toggleMacProxy()'),
        }] : []),
        {
          label:   'Bust Cache',
          type:    'checkbox',
          checked: bustCacheEnabled,
          click:   () => {
            bustCacheEnabled = !bustCacheEnabled
            js('bustCache()')
            setupMenu()   // rebuild so the checkmark updates
          },
        },
      ],
    },
    {
      label: 'Tools',
      submenu: [
        { label: 'VPN Mode',     click: () => js('openVpnMode()') },
        { label: 'Breakpoints',  click: () => js('openBreakpoints()') },
        { type: 'separator' },
        { label: 'Map Local',    click: () => js('openMapLocal()') },
        { label: 'Map Remote',   click: () => js('openMapRemote()') },
        { label: 'Highlight',    click: () => js('openHighlight()') },
        { label: 'Scripts',      click: () => js('openScripting()') },
        { type: 'separator' },
        {
          label: 'Certificate Setup',
          submenu: [
            { label: 'Android Emulator',  click: () => js("openCertSetup('android_emulator')") },
            { label: 'Android Device',    click: () => js("openCertSetup('android_device')") },
            { type: 'separator' },
            { label: 'iOS Simulator',     click: () => js("openCertSetup('ios_simulator')") },
            { label: 'iOS Device',        click: () => js("openCertSetup('ios_device')") },
            { type: 'separator' },
            { label: 'Browser / Desktop', click: () => js("openCertSetup('browser')") },
          ],
        },
        { type: 'separator' },
        {
          label: 'Throttle',
          submenu: [
            { label: 'No Throttling', click: () => js("setThrottle('None')") },
            { label: 'Fast 3G',       click: () => js("setThrottle('Fast 3G')") },
            { label: 'Slow 3G',       click: () => js("setThrottle('Slow 3G')") },
          ],
        },
      ],
    },
    {
      label: 'View',
      submenu: [
        {
          label: 'Theme',
          submenu: [
            { label: 'Dark',     type: 'radio', checked: currentTheme === 'dark',     click: () => setTheme('dark') },
            { label: 'Midnight', type: 'radio', checked: currentTheme === 'midnight', click: () => setTheme('midnight') },
            { label: 'Ocean',    type: 'radio', checked: currentTheme === 'ocean',    click: () => setTheme('ocean') },
            { label: 'Crimson',  type: 'radio', checked: currentTheme === 'crimson',  click: () => setTheme('crimson') },
            { label: 'Ember',  type: 'radio', checked: currentTheme === 'ember',  click: () => setTheme('ember') },
            { label: 'Light',    type: 'radio', checked: currentTheme === 'light',    click: () => setTheme('light') },
          ],
        },
        {
          label: 'Toolbar',
          submenu: Object.entries({
            vpnMode: 'VPN Mode', breakpoints: 'Breakpoints', mapLocal: 'Map Local',
            mapRemote: 'Map Remote', highlights: 'Highlights', scripts: 'Scripts',
          }).flatMap(([key, label], i) => [
            ...(i === 1 ? [{ type: 'separator' }] : []),  // separator before Breakpoints
            {
              label, type: 'checkbox', checked: toolbarVisibility[key],
              click: () => {
                toolbarVisibility[key] = !toolbarVisibility[key]
                win?.webContents.send('toolbar:set', { ...toolbarVisibility })
                setupMenu()
              },
            },
          ]).concat([
            { type: 'separator' },
            ...[
              'certificates',
              'throttle',
              'bustCache',
              ...(process.platform === 'darwin' ? ['osProxy'] : []),
            ].map((key) => ({
              label: { certificates: 'Certificates', throttle: 'Throttle', bustCache: 'Bust Cache', osProxy: 'OS Proxy' }[key],
              type: 'checkbox', checked: toolbarVisibility[key],
              click: () => {
                toolbarVisibility[key] = !toolbarVisibility[key]
                win?.webContents.send('toolbar:set', { ...toolbarVisibility })
                setupMenu()
              },
            })),
          ]),
        },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Check for Updates',
          click: () => win?.webContents.executeJavaScript('window.__op?.checkForUpdates()'),
        },
        { type: 'separator' },
        {
          label: 'Export Settings…',
          click: () => win?.webContents.executeJavaScript('window.__op?.exportSettings()'),
        },
        {
          label: 'Import Settings…',
          click: () => win?.webContents.executeJavaScript('window.__op?.importSettings()'),
        },
        {
          label: 'Reset All Preferences…',
          click: async () => {
            const { response } = await dialog.showMessageBox(win, {
              type:    'warning',
              buttons: ['Reset', 'Cancel'],
              defaultId: 1,
              cancelId:  1,
              title:   'Reset All Preferences',
              message: 'Reset all preferences to defaults?',
              detail:  'This will clear all saved settings, rules, and traffic — like a fresh install. This cannot be undone.',
            })
            if (response === 0) win?.webContents.send('prefs:reset')
          },
        },
        { type: 'separator' },
        {
          label: `About OpenProxy v${app.getVersion()}`,
          click: () => win?.webContents.executeJavaScript('window.__op?.showAbout()'),
        },
      ],
    },
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

function setTheme(id) {
  currentTheme = id
  win?.webContents.send('theme:set', id)
  if (process.platform === 'win32' && win) {
    const colors = OVERLAY_COLORS[id] || OVERLAY_COLORS.dark
    win.setTitleBarOverlay({ ...colors, height: 38 })
  }
  setupMenu()
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function showWindow () {
  if (!win) return
  win.show()
  win.focus()
}

function quitApp () {
  isQuitting = true
  if (pythonProcess) pythonProcess.kill()
  app.quit()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // Clear quarantine from the entire .app bundle on first launch after zip
  // extraction. Must run before any Electron helper or Python process spawns.
  if (app.isPackaged) {
    const bundle = getAppBundlePath()
    if (bundle) clearQuarantine(bundle)
  }

  setupIPC()
  setupTray()
  setupMenu()
  createWindow()

  const index = app.isPackaged
    ? path.join(process.resourcesPath, 'ui', 'dist', 'index.html')
    : path.join(__dirname, '..', 'ui', 'dist', 'index.html')

  // In dev, build UI first; in production the dist is already bundled
  if (!app.isPackaged) await buildUI()

  // Load UI immediately — the frontend's WS reconnect logic handles backend not being ready yet
  win.loadFile(index)

  // Start Python in parallel — no need to block the renderer on it
  startPython()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    else showWindow()
  })
})

app.on('before-quit', () => {
  isQuitting = true
  if (pythonProcess) pythonProcess.kill()
})

// Prevent default quit on all-windows-closed so tray keeps the app alive
app.on('window-all-closed', e => e.preventDefault())

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform:         process.platform,
  minimize:         ()           => ipcRenderer.send('window:minimize'),
  toggleFullscreen: ()           => ipcRenderer.send('window:toggleFullscreen'),
  zoom:             ()           => ipcRenderer.send('window:zoom'),
  close:            ()           => ipcRenderer.send('window:close'),
  quit:             ()           => ipcRenderer.send('window:quit'),
  openExternal:     url          => ipcRenderer.send('shell:openExternal', url),
  saveFile:         (name, data) => ipcRenderer.invoke('dialog:saveFile', { filename: name, content: data }),
  bustCacheSync:    (val)        => ipcRenderer.send('menu:bustCacheSync', val),
  macosProxySync:   (val)        => ipcRenderer.send('menu:macosProxySync', val),
  proxyHttp2Sync:         (val)  => ipcRenderer.send('menu:proxyHttp2Sync', val),
  proxyUpstreamCertSync:  (val)  => ipcRenderer.send('menu:proxyUpstreamCertSync', val),
  proxyHostFilterModeSync: (mode)=> ipcRenderer.send('menu:proxyHostFilterModeSync', mode),
  themeChanged:     (id)         => ipcRenderer.send('theme:changed', id),
  onSetTheme:       (cb)         => ipcRenderer.on('theme:set', (_e, id) => cb(id)),
  onMaximizeChange: (cb)         => ipcRenderer.on('window:maximized', (_e, v) => cb(v)),
  toolbarSyncToMain: (vis)       => ipcRenderer.send('toolbar:syncToMain', vis),
  onToolbarSet:     (cb)         => ipcRenderer.on('toolbar:set', (_e, vis) => cb(vis)),
  selectFile:          (opts) => ipcRenderer.invoke('dialog:selectFile', opts),
  onResetPreferences:  (cb)   => ipcRenderer.on('prefs:reset', () => cb()),
})

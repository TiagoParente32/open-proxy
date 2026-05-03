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
  themeChanged:     (id)         => ipcRenderer.send('theme:changed', id),
  onSetTheme:       (cb)         => ipcRenderer.on('theme:set', (_e, id) => cb(id)),
  onMaximizeChange: (cb)         => ipcRenderer.on('window:maximized', (_e, v) => cb(v)),
})

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform:         process.platform,
  minimize:         ()           => ipcRenderer.send('window:minimize'),
  toggleFullscreen: ()           => ipcRenderer.send('window:toggleFullscreen'),
  zoom:             ()           => ipcRenderer.send('window:zoom'),
  close:            ()           => ipcRenderer.send('window:close'),
  openExternal:     url          => ipcRenderer.send('shell:openExternal', url),
  saveFile:         (name, data) => ipcRenderer.invoke('dialog:saveFile', { filename: name, content: data }),
})

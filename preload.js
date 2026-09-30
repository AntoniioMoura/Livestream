const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('liveChat', {
	getSettings: () => ipcRenderer.invoke('live:settings:get'),
	saveSettings: (settings) => ipcRenderer.invoke('live:settings:save', settings),
	listWorldbuildingDocuments: () => ipcRenderer.invoke('live:worldbuilding:list'),
	start: (settings) => ipcRenderer.invoke('live:start', settings),
	acknowledgeRender: () => ipcRenderer.send('live:rendered'),
	onEvent: (callback) => {
		const listener = (_event, data) => callback(data);
		ipcRenderer.on('live:event', listener);
		return () => ipcRenderer.removeListener('live:event', listener);
	}
});

contextBridge.exposeInMainWorld('learningReport', {
	onData: (callback) => {
		const listener = (_event, data) => callback(data);
		ipcRenderer.on('report:data', listener);
		return () => ipcRenderer.removeListener('report:data', listener);
	},
	getStylesheet: () => ipcRenderer.invoke('report:styles:get'),
	saveHtml: (html) => ipcRenderer.invoke('report:html:save', html),
	saveImage: () => ipcRenderer.invoke('report:image:save'),
	back: () => ipcRenderer.send('report:back'),
	quit: () => ipcRenderer.send('report:quit')
});
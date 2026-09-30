const { app, BrowserWindow, dialog, globalShortcut, ipcMain, screen } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

let configWindow;
let overlayWindow;
let reportWindow;
let liveProcess;
let reportProcess;
let mousePassthrough = true;
let overlayRefreshTimer;
let lastSettings;
let reportAfterLive = false;
let latestReport;
let reportPageLoaded = false;
let appIsQuitting = false;
const personaNames = ['Jake', 'Lulu_Cat', 'kevin_noob', 'Lord_meme'];
const worldbuildingExtensions = new Set(['.md', '.markdown', '.txt', '.json']);

function listWorldbuildingDocuments() {
    const directory = path.join(__dirname, 'worldbuilding');
    fs.mkdirSync(directory, { recursive: true });

    return fs.readdirSync(directory, { withFileTypes: true })
        .filter((entry) => entry.isFile() && worldbuildingExtensions.has(path.extname(entry.name).toLowerCase()))
        .map((entry) => entry.name)
        .sort((left, right) => left.localeCompare(right));
}

function settingsPath() {
    return path.join(app.getPath('userData'), 'live-settings.json');
}

function normalizeSettings(settings) {
    const values = settings && typeof settings === 'object' ? settings : {};
    const rawPersonas = values.personas && typeof values.personas === 'object' ? values.personas : {};
    const interval = Number(values.silenceInterval);
    const requestedWorldbuildingFile = typeof values.worldbuildingFile === 'string'
        ? values.worldbuildingFile.trim()
        : '';
    const worldbuildingFile = path.basename(requestedWorldbuildingFile) === requestedWorldbuildingFile
        && worldbuildingExtensions.has(path.extname(requestedWorldbuildingFile).toLowerCase())
        ? requestedWorldbuildingFile
        : '';
    const personas = {};

    for (const name of personaNames) {
        if (typeof rawPersonas[name] === 'string' && rawPersonas[name].trim()) {
            personas[name] = rawPersonas[name].trim().slice(0, 180);
        }
    }

    return {
        theme: typeof values.theme === 'string' ? values.theme.trim().slice(0, 120) : 'Gameplay e conversa com o chat',
        streamerName: typeof values.streamerName === 'string'
            ? values.streamerName.trim().replace(/\s+/g, ' ').slice(0, 40)
            : '',
        language: ['en', 'pt'].includes(values.language) ? values.language : 'en',
        complexity: ['simple', 'normal', 'advanced'].includes(values.complexity) ? values.complexity : 'normal',
        responseCount: ['1', '2', '3', 'random'].includes(String(values.responseCount)) ? String(values.responseCount) : 'random',
        silenceChat: typeof values.silenceChat === 'boolean' ? values.silenceChat : true,
        silenceInterval: Number.isFinite(interval) ? Math.max(10, Math.min(60, Math.round(interval))) : 25,
        personas,
        worldbuildingFile
    };
}

function loadSettings() {
    try {
        return normalizeSettings(JSON.parse(fs.readFileSync(settingsPath(), 'utf8')));
    } catch {
        return null;
    }
}

function saveSettings(settings) {
    const normalized = normalizeSettings(settings);
    const filePath = settingsPath();
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
    return normalized;
}

function sendEvent(event) {
    for (const window of [configWindow, overlayWindow]) {
        if (window && !window.isDestroyed()) {
            window.webContents.send('live:event', event);
        }
    }

    if (overlayWindow && !overlayWindow.isDestroyed()) {
        if (event.tipo === 'message') {
            console.log(`[live-event] ${event.tipo_mensagem}:${event.nome}`);
        }
        if (event.tipo === 'status' && event.status === 'live' && !overlayRefreshTimer) {
            overlayRefreshTimer = setInterval(() => {
                if (overlayWindow && !overlayWindow.isDestroyed()) {
                    overlayWindow.webContents.invalidate();
                }
            }, 250);
        }
    }
}

function sendReport(report) {
    latestReport = report;
    if (reportWindow && !reportWindow.isDestroyed() && reportPageLoaded) {
        reportWindow.webContents.send('report:data', report);
    }
}

function createReportWindow() {
    if (reportWindow && !reportWindow.isDestroyed()) {
        reportWindow.focus();
        return;
    }

    reportPageLoaded = false;
    reportWindow = new BrowserWindow({
        width: 1320,
        height: 1160,
        minWidth: 900,
        minHeight: 680,
        backgroundColor: '#f2f2ed',
        autoHideMenuBar: true,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });
    reportWindow.loadFile('report.html');
    reportWindow.once('ready-to-show', () => {
        reportPageLoaded = true;
        reportWindow.show();
        if (latestReport) reportWindow.webContents.send('report:data', latestReport);
    });
    reportWindow.on('closed', () => {
        reportWindow = null;
        reportPageLoaded = false;
        if (!appIsQuitting && configWindow && !configWindow.isDestroyed()) configWindow.show();
    });
}

function startReportGeneration() {
    if (configWindow && !configWindow.isDestroyed()) configWindow.hide();
    latestReport = null;
    createReportWindow();

    const python = process.env.PYTHON_EXECUTABLE || 'python';
    const script = path.join(__dirname, 'gerar_relatorio.py');
    reportProcess = spawn(python, ['-u', script], {
        cwd: __dirname,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true
    });

    let output = '';
    reportProcess.stdout.setEncoding('utf8');
    reportProcess.stdout.on('data', (chunk) => {
        output += chunk;
    });
    reportProcess.stderr.setEncoding('utf8');
    reportProcess.stderr.on('data', (chunk) => {
        console.error('[gerar_relatorio]', chunk.trim());
    });
    reportProcess.on('error', (error) => {
        reportProcess = null;
        sendReport({ error: `Não foi possível iniciar o relatório: ${error.message}` });
    });
    reportProcess.on('close', (code) => {
        reportProcess = null;
        try {
            sendReport(JSON.parse(output.trim()));
        } catch {
            sendReport({ error: output.trim() || `O gerador de relatório encerrou com código ${code}.` });
        }
    });
}

ipcMain.on('live:rendered', () => {
    if (!overlayWindow || overlayWindow.isDestroyed()) return;
    overlayWindow.webContents.invalidate();
    console.log('[live-overlay] event rendered');
});

function createOverlayWindow(settings) {
    const { workArea } = screen.getPrimaryDisplay();

    overlayWindow = new BrowserWindow({
        x: workArea.x + workArea.width - 430,
        y: workArea.y + 70,
        width: 410,
        height: 620,
        minWidth: 300,
        minHeight: 180,
        maxWidth: 620,
        maxHeight: 1000,
        transparent: true,
        frame: false,
        hasShadow: false,
        alwaysOnTop: true,
        backgroundColor: '#00000000',
        autoHideMenuBar: true,
        show: false,

        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            autoplayPolicy: 'no-user-gesture-required',
            backgroundThrottling: false
        }
    });

    overlayWindow.setAlwaysOnTop(true, 'screen-saver');
    overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    overlayWindow.loadFile('index.html');
    overlayWindow.once('ready-to-show', () => {
        overlayWindow.show();
        overlayWindow.setIgnoreMouseEvents(mousePassthrough, { forward: true });
        startSimulator(settings);
    });
    overlayWindow.on('closed', () => {
        overlayWindow = null;
        clearInterval(overlayRefreshTimer);
        overlayRefreshTimer = null;
        if (liveProcess) stopSimulator();
        if (!appIsQuitting && !reportWindow && configWindow && !configWindow.isDestroyed()) configWindow.show();
    });
}

function startSimulator(settings) {
    const python = process.env.PYTHON_EXECUTABLE || 'python';
    const script = path.join(__dirname, 'live_simulator.py');
    liveProcess = spawn(python, ['-u', script, '--config-json', JSON.stringify(settings)], {
        cwd: __dirname,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true
    });

    let output = '';
    liveProcess.stdout.setEncoding('utf8');
    liveProcess.stdout.on('data', (chunk) => {
        output += chunk;
        const linhas = output.split(/\r?\n/);
        output = linhas.pop();

        for (const linha of linhas) {
            if (!linha.trim()) continue;
            try {
                sendEvent(JSON.parse(linha));
            } catch {
                sendEvent({ tipo: 'error', mensagem: linha });
            }
        }
    });

    liveProcess.stderr.setEncoding('utf8');
    liveProcess.stderr.on('data', (chunk) => {
        console.error('[live_simulator]', chunk.trim());
    });

    liveProcess.on('error', (error) => {
        sendEvent({ tipo: 'error', mensagem: `Não foi possível iniciar o Python: ${error.message}` });
        liveProcess = null;
    });

    liveProcess.on('close', (code) => {
        const shouldGenerateReport = reportAfterLive;
        reportAfterLive = false;
        if (output.trim()) {
            try {
                sendEvent(JSON.parse(output));
            } catch {
                sendEvent({ tipo: 'error', mensagem: output.trim() });
            }
        }
        if (code !== 0 && !shouldGenerateReport) {
            sendEvent({ tipo: 'error', mensagem: `O simulador encerrou com código ${code}.` });
        }
        liveProcess = null;
        sendEvent({ tipo: 'status', status: 'idle', mensagem: 'Simulador desconectado' });
        clearInterval(overlayRefreshTimer);
        overlayRefreshTimer = null;
        if (shouldGenerateReport) startReportGeneration();
        if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.close();
        if (!shouldGenerateReport && configWindow && !configWindow.isDestroyed()) configWindow.show();
    });

    sendEvent({ tipo: 'status', status: 'starting', mensagem: 'Iniciando captura de voz...' });
}

function startLive(settings) {
    if (liveProcess || overlayWindow) {
        return { started: false, reason: 'already-running' };
    }

    lastSettings = saveSettings(settings);
    if (configWindow && !configWindow.isDestroyed()) configWindow.hide();
    createOverlayWindow(lastSettings);
    return { started: true };
}

function stopSimulator(generateReport = false) {
    if (liveProcess) {
        reportAfterLive = generateReport;
        liveProcess.kill(); // Força o encerramento imediato e limpo do processo
        sendEvent({ tipo: 'status', status: 'stopping', mensagem: 'Encerrando a live...' });
    }
}

ipcMain.handle('live:settings:get', () => loadSettings());
ipcMain.handle('live:settings:save', (_event, settings) => saveSettings(settings));
ipcMain.handle('live:worldbuilding:list', () => listWorldbuildingDocuments());
ipcMain.handle('live:start', (_event, settings) => startLive(settings));
ipcMain.handle('report:styles:get', () => fs.readFileSync(path.join(__dirname, 'report.css'), 'utf8'));
ipcMain.handle('report:html:save', async (_event, html) => {
    if (typeof html !== 'string' || html.length > 5_000_000) {
        throw new Error('O conteúdo HTML do relatório é inválido.');
    }
    const result = await dialog.showSaveDialog(reportWindow, {
        title: 'Salvar relatório em HTML',
        defaultPath: 'relatorio-de-ingles.html',
        filters: [{ name: 'Página HTML', extensions: ['html'] }]
    });
    if (result.canceled || !result.filePath) return { canceled: true };
    fs.writeFileSync(result.filePath, html, 'utf8');
    return { canceled: false, filePath: result.filePath };
});
ipcMain.handle('report:image:save', async () => {
    if (!reportWindow || reportWindow.isDestroyed()) throw new Error('A janela do relatório não está aberta.');
    const result = await dialog.showSaveDialog(reportWindow, {
        title: 'Salvar imagem do relatório',
        defaultPath: 'relatorio-de-ingles.png',
        filters: [{ name: 'Imagem PNG', extensions: ['png'] }]
    });
    if (result.canceled || !result.filePath) return { canceled: true };
    const image = await reportWindow.webContents.capturePage();
    fs.writeFileSync(result.filePath, image.toPNG());
    return { canceled: false, filePath: result.filePath };
});
ipcMain.on('report:back', () => {
    if (reportWindow && !reportWindow.isDestroyed()) reportWindow.close();
});
ipcMain.on('report:quit', () => app.quit());

app.whenReady().then(() => {
    console.log('[startup] abrindo tela de configuração');
    configWindow = new BrowserWindow({
        width: 980,
        height: 760,
        minWidth: 720,
        minHeight: 620,
        backgroundColor: '#171a19',
        autoHideMenuBar: true,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });
    configWindow.loadFile('config.html');
    configWindow.once('ready-to-show', () => configWindow.show());
    configWindow.on('closed', () => {
        configWindow = null;
        if (liveProcess) stopSimulator();
    });

    globalShortcut.register('CommandOrControl+Shift+F10', () => {
        if (liveProcess) stopSimulator(true);
        else if (lastSettings) startLive(lastSettings);
    });
    globalShortcut.register('CommandOrControl+Shift+F11', () => {
        if (!overlayWindow) return;
        mousePassthrough = !mousePassthrough;
        overlayWindow.setIgnoreMouseEvents(mousePassthrough, { forward: true });
        sendEvent({ tipo: 'interaction', enabled: !mousePassthrough });
    });
});

app.on('before-quit', () => {
    appIsQuitting = true;
    clearInterval(overlayRefreshTimer);
    if (liveProcess) liveProcess.kill();
    if (reportProcess) reportProcess.kill();
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});
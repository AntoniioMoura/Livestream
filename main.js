const { app, BrowserWindow, dialog, globalShortcut, ipcMain, screen } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

let configWindow;
let overlayWindow;
let teacherWindow;
let teacherMoveMode = false;
let reportWindow;
let liveProcess;
let liveStopTimer;
let reportProcess;
let mousePassthrough = true;
let overlayRefreshTimer;
let lastSettings;
let reportAfterLive = false;
let latestReport;
let reportPageLoaded = false;
let appIsQuitting = false;
let quitWhenLiveStops = false;
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
        worldbuildingFile,
        useTranslator: typeof values.useTranslator === 'boolean' ? values.useTranslator : false
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
    for (const window of [configWindow, overlayWindow, teacherWindow]) {
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
    createTeacherWindow(workArea);
    overlayWindow.once('ready-to-show', () => {
        overlayWindow.show();
        overlayWindow.setIgnoreMouseEvents(mousePassthrough, { forward: true });
        startSimulator(settings);
    });
    overlayWindow.on('closed', () => {
        overlayWindow = null;
        if (teacherWindow && !teacherWindow.isDestroyed()) teacherWindow.close();
        clearInterval(overlayRefreshTimer);
        overlayRefreshTimer = null;
        if (liveProcess) stopSimulator();
        if (!appIsQuitting && !reportWindow && configWindow && !configWindow.isDestroyed()) configWindow.show();
    });
}

function createTeacherWindow(workArea) {
    teacherWindow = new BrowserWindow({
        x: workArea.x + 24,
        y: workArea.y + 70,
        width: 340,
        height: 170,
        minWidth: 280,
        minHeight: 130,
        maxWidth: 420,
        maxHeight: 260,
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
            backgroundThrottling: false
        }
    });

    teacherWindow.setAlwaysOnTop(true, 'screen-saver');
    teacherWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    teacherWindow.loadFile('teacher.html');
    teacherWindow.once('ready-to-show', () => {
        teacherWindow.show();
        teacherWindow.setIgnoreMouseEvents(!teacherMoveMode, { forward: true });
    });
    teacherWindow.on('closed', () => {
        teacherWindow = null;
        teacherMoveMode = false;
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
        clearTimeout(liveStopTimer);
        liveStopTimer = null;
        sendEvent({ tipo: 'error', mensagem: `Não foi possível iniciar o Python: ${error.message}` });
        liveProcess = null;
    });

    liveProcess.on('close', (code) => {
        const shouldGenerateReport = reportAfterLive;
        const shouldQuit = quitWhenLiveStops;
        reportAfterLive = false;
        clearTimeout(liveStopTimer);
        liveStopTimer = null;
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
        if (shouldGenerateReport && !shouldQuit) startReportGeneration();
        if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.close();
        if (shouldQuit) {
            quitWhenLiveStops = false;
            app.quit();
            return;
        }
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
    if (!liveProcess) return;

    reportAfterLive = reportAfterLive || generateReport;
    sendEvent({ tipo: 'status', status: 'stopping', mensagem: 'Encerrando a live...' });

    // Encerra o processo imediatamente. Como o Python já salvou os arquivos no disco,
    // o evento 'close' será disparado na sequência e o relatório será aberto normalmente.
    liveProcess.kill();
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
    globalShortcut.register('CommandOrControl+Shift+F12', () => {
        if (!teacherWindow || teacherWindow.isDestroyed()) return;
        teacherMoveMode = !teacherMoveMode;
        teacherWindow.setIgnoreMouseEvents(!teacherMoveMode, { forward: true });
        sendEvent({ tipo: 'teacher_move_mode', enabled: teacherMoveMode });
        console.log(`[teacher-overlay] move mode ${teacherMoveMode ? 'enabled' : 'disabled'}`);
    });
});

app.on('before-quit', (event) => {
    clearInterval(overlayRefreshTimer);
    if (liveProcess && !quitWhenLiveStops) {
        event.preventDefault();
        appIsQuitting = true;
        quitWhenLiveStops = true;
        reportAfterLive = false;
        stopSimulator();
        return;
    }

    appIsQuitting = true;
    if (reportProcess) reportProcess.kill();
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});
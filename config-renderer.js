const form = document.getElementById('setup-form');
const startButton = document.getElementById('start-button');
const feedback = document.getElementById('form-feedback');
const themeInput = document.getElementById('stream-theme');
const streamerNameInput = document.getElementById('streamer-name');
const worldbuildingInput = document.getElementById('worldbuilding-document');
const worldbuildingHint = document.getElementById('worldbuilding-hint');
const languageInput = document.getElementById('language');
const complexityInput = document.getElementById('complexity');
const responsesInput = document.getElementById('responses');
const silenceChatInput = document.getElementById('silence-chat');
const useTranslatorInput = document.getElementById('use-translator');
const silenceIntervalInput = document.getElementById('silence-interval');
const intervalValue = document.getElementById('interval-value');
const intervalField = document.getElementById('interval-field');
const previewTheme = document.getElementById('preview-theme');
const previewComplexity = document.getElementById('preview-complexity');
const personaInputs = [...document.querySelectorAll('[data-persona]')];

const complexityCopy = {
    simple: 'Vocabulário simples e mensagens diretas',
    normal: 'Respostas naturais e equilibradas',
    advanced: 'Gírias e referências mais específicas do jogo'
};

function collectSettings() {
    return {
        theme: themeInput.value.trim(),
        streamerName: streamerNameInput.value.trim(),
        worldbuildingFile: worldbuildingInput.value,
        language: languageInput.value,
        complexity: complexityInput.value,
        responseCount: responsesInput.value,
        silenceChat: silenceChatInput.checked,
        useTranslator: useTranslatorInput.checked,
        silenceInterval: Number(silenceIntervalInput.value),
        personas: Object.fromEntries(personaInputs.map((input) => [input.dataset.persona, input.value.trim()]))
    };
}

function applySettings(settings) {
    if (typeof settings.theme === 'string') themeInput.value = settings.theme;
    if (typeof settings.streamerName === 'string') streamerNameInput.value = settings.streamerName;
    if ([...worldbuildingInput.options].some((option) => option.value === settings.worldbuildingFile)) {
        worldbuildingInput.value = settings.worldbuildingFile;
    }
    if (['en', 'pt'].includes(settings.language)) languageInput.value = settings.language;
    if (['simple', 'normal', 'advanced'].includes(settings.complexity)) complexityInput.value = settings.complexity;
    if (['1', '2', '3', 'random'].includes(String(settings.responseCount))) responsesInput.value = String(settings.responseCount);
    if (typeof settings.silenceChat === 'boolean') silenceChatInput.checked = settings.silenceChat;
    if (typeof settings.useTranslator === 'boolean') useTranslatorInput.checked = settings.useTranslator;
    if (Number.isFinite(settings.silenceInterval)) silenceIntervalInput.value = String(settings.silenceInterval);

    if (settings.personas && typeof settings.personas === 'object') {
        for (const input of personaInputs) {
            if (typeof settings.personas[input.dataset.persona] === 'string') {
                input.value = settings.personas[input.dataset.persona];
            }
        }
    }
}

function updatePreview() {
    previewTheme.textContent = themeInput.value.trim() || 'Tema da transmissão';
    previewComplexity.textContent = complexityCopy[complexityInput.value];
    intervalValue.value = `${silenceIntervalInput.value} s`;
    intervalValue.textContent = `${silenceIntervalInput.value} s`;
    intervalField.classList.toggle('is-disabled', !silenceChatInput.checked);
    silenceIntervalInput.disabled = !silenceChatInput.checked;
}

let saveTimer;
function scheduleSettingsSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(async () => {
        try {
            await window.liveChat?.saveSettings(collectSettings());
            feedback.textContent = 'Preferências salvas neste dispositivo';
        } catch (error) {
            feedback.textContent = `Não foi possível salvar as preferências: ${error.message}`;
        }
    }, 400);
}

form.addEventListener('input', () => {
    updatePreview();
    scheduleSettingsSave();
});
form.addEventListener('change', () => {
    updatePreview();
    scheduleSettingsSave();
});

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!window.liveChat) {
        feedback.textContent = 'Abra esta tela pelo aplicativo Electron para iniciar.';
        return;
    }

    const settings = collectSettings();

    startButton.disabled = true;
    startButton.innerHTML = '<span class="loading-mark"></span>Preparando';
    feedback.textContent = 'Abrindo o microfone e preparando o chat...';

    try {
        await window.liveChat.saveSettings(settings);
        const result = await window.liveChat.start(settings);
        if (!result?.started) throw new Error('Já existe uma transmissão em andamento.');
    } catch (error) {
        feedback.textContent = error.message || 'Não foi possível iniciar a live.';
        startButton.disabled = false;
        startButton.innerHTML = '<span class="play-mark"></span>Iniciar live';
    }
});

window.liveChat?.onEvent((event) => {
    if (event.tipo === 'error') {
        feedback.textContent = event.mensagem;
        startButton.disabled = false;
        startButton.innerHTML = '<span class="play-mark"></span>Iniciar live';
    }
});

async function restoreSettings() {
    try {
        const settings = await window.liveChat?.getSettings();
        await refreshWorldbuildingDocuments(settings?.worldbuildingFile || '');
        if (settings) applySettings(settings);
    } catch (error) {
        feedback.textContent = `Não foi possível carregar as preferências: ${error.message}`;
    }
    updatePreview();
}

async function refreshWorldbuildingDocuments(selectedFile = worldbuildingInput.value) {
    const documents = await window.liveChat?.listWorldbuildingDocuments() || [];
    worldbuildingInput.replaceChildren(new Option('Sem documento de contexto', ''));
    for (const documentName of documents) {
        worldbuildingInput.add(new Option(documentName, documentName));
    }
    worldbuildingInput.disabled = documents.length === 0;
    worldbuildingHint.textContent = documents.length
        ? 'Arquivos .md, .txt e .json; até 1.800 caracteres relevantes por análise'
        : 'Nenhum documento compatível encontrado na pasta worldbuilding';
    worldbuildingInput.value = documents.includes(selectedFile) ? selectedFile : '';
}

worldbuildingInput.addEventListener('focus', async () => {
    try {
        await refreshWorldbuildingDocuments();
    } catch (error) {
        feedback.textContent = `Não foi possível atualizar os documentos: ${error.message}`;
    }
});

restoreSettings();

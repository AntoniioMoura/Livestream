const reportRoot = document.getElementById('report-document');
const loadingOverlay = document.getElementById('loading-overlay');
const reportSummary = document.getElementById('report-summary');
const reportNotice = document.getElementById('report-notice');
const exportFeedback = document.getElementById('export-feedback');

const metricLabels = {
    fluency: 'Fluidez textual',
    grammar: 'Gramática',
    vocabulary: 'Vocabulário',
    clarity: 'Clareza'
};

function appendTextList(containerId, values, emptyText) {
    const container = document.getElementById(containerId);
    container.replaceChildren();
    const items = Array.isArray(values) ? values : [];
    if (!items.length) {
        const empty = document.createElement('li');
        empty.className = 'empty-list';
        empty.textContent = emptyText;
        container.append(empty);
        return;
    }

    for (const value of items) {
        const item = document.createElement('li');
        item.textContent = value;
        container.append(item);
    }
}

function appendStudyItems(containerId, items, fields, emptyText) {
    const container = document.getElementById(containerId);
    container.replaceChildren();
    if (!Array.isArray(items) || !items.length) {
        const empty = document.createElement('p');
        empty.className = 'no-study-items';
        empty.textContent = emptyText;
        container.append(empty);
        return;
    }

    for (const entry of items) {
        const item = document.createElement('article');
        item.className = 'study-item';
        const originalLabel = document.createElement('p');
        originalLabel.className = 'study-label';
        originalLabel.textContent = fields.originalLabel;
        const original = document.createElement('p');
        original.className = 'study-original';
        original.textContent = entry.original || '';
        const suggestion = document.createElement('p');
        suggestion.className = 'study-suggestion';
        suggestion.textContent = fields.suggestion(entry);
        const explanation = document.createElement('p');
        explanation.className = 'study-explanation';
        explanation.textContent = fields.explanation(entry);
        item.append(originalLabel, original, suggestion, explanation);
        container.append(item);
    }
}

function renderReport(report) {
    loadingOverlay.hidden = true;
    reportNotice.hidden = true;
    reportNotice.textContent = '';
    reportSummary.textContent = report.summary || 'Relatório da sessão concluído.';
    document.getElementById('report-date').textContent = new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'long',
        timeStyle: 'short'
    }).format(new Date());

    const metrics = report.metrics && typeof report.metrics === 'object' ? report.metrics : {};
    const chart = document.getElementById('metrics-chart');
    chart.replaceChildren();
    for (const [key, label] of Object.entries(metricLabels)) {
        const score = Math.max(0, Math.min(100, Number(metrics[key]) || 0));
        const row = document.createElement('div');
        row.className = 'metric-row';
        const name = document.createElement('span');
        name.className = 'metric-name';
        name.textContent = label;
        const track = document.createElement('span');
        track.className = 'metric-track';
        track.setAttribute('role', 'meter');
        track.setAttribute('aria-label', label);
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', '100');
        track.setAttribute('aria-valuenow', String(score));
        const fill = document.createElement('span');
        fill.className = 'metric-fill';
        fill.style.width = `${score}%`;
        track.append(fill);
        const scoreText = document.createElement('span');
        scoreText.className = 'metric-score';
        scoreText.textContent = String(score).padStart(2, '0');
        row.append(name, track, scoreText);
        chart.append(row);
    }

    appendTextList('strengths-list', report.strengths, 'Sem observações suficientes nesta sessão.');
    appendTextList('weaknesses-list', report.weaknesses, 'Nenhum ponto de atenção identificado.');
    appendTextList('improvements-list', report.improvements, 'Continue praticando para gerar próximas sugestões.');
    appendStudyItems('corrections-list', report.corrections, {
        originalLabel: 'FRASE REGISTRADA',
        suggestion: (entry) => entry.corrected,
        explanation: (entry) => entry.explanation
    }, 'Não houve correções específicas nesta sessão.');
    appendStudyItems('vocabulary-list', report.vocabulary, {
        originalLabel: 'CONTEXTO / EXPRESSÃO',
        suggestion: (entry) => entry.suggestion,
        explanation: (entry) => entry.reason
    }, 'Sem sugestões de vocabulário para esta sessão.');

    if (!report.hasTranscript || report.error) {
        reportNotice.hidden = false;
        reportNotice.textContent = report.error || 'Nenhuma fala foi registrada nesta sessão. O relatório traz orientações gerais, sem análise personalizada.';
    }
}

async function exportHtml() {
    exportFeedback.textContent = 'Preparando arquivo HTML...';
    try {
        const stylesheet = await window.learningReport.getStylesheet();
        const content = reportRoot.cloneNode(true);
        content.querySelectorAll('[data-export-ignore]').forEach((element) => element.remove());
        const html = `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Relatório da live · Prática de inglês</title><style>${stylesheet}</style></head><body>${content.outerHTML}</body></html>`;
        const result = await window.learningReport.saveHtml(html);
        exportFeedback.textContent = result.canceled ? 'Download cancelado.' : 'Relatório HTML salvo.';
    } catch (error) {
        exportFeedback.textContent = `Falha ao salvar HTML: ${error.message}`;
    }
}

async function exportImage() {
    exportFeedback.textContent = 'Capturando a página...';
    try {
        const result = await window.learningReport.saveImage();
        exportFeedback.textContent = result.canceled ? 'Download cancelado.' : 'Imagem PNG salva.';
    } catch (error) {
        exportFeedback.textContent = `Falha ao salvar imagem: ${error.message}`;
    }
}

document.getElementById('save-html').addEventListener('click', exportHtml);
document.getElementById('save-image').addEventListener('click', exportImage);
document.getElementById('back-button').addEventListener('click', () => window.learningReport.back());
document.getElementById('quit-button').addEventListener('click', () => window.learningReport.quit());

if (window.learningReport) {
    window.learningReport.onData(renderReport);
} else {
    loadingOverlay.hidden = true;
    reportNotice.hidden = false;
    reportNotice.textContent = 'Abra esta página pelo aplicativo Live Room para carregar um relatório.';
}

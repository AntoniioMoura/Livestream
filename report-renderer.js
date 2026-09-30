const reportRoot = document.getElementById('report-document');
const loadingOverlay = document.getElementById('loading-overlay');
const reportSummary = document.getElementById('report-summary');
const reportNotice = document.getElementById('report-notice');
const exportFeedback = document.getElementById('export-feedback');

const metricLabels = {
    fluency: 'Fluidez e organização',
    grammar: 'Gramática',
    vocabulary: 'Vocabulário',
    clarity: 'Clareza'
};

const confidenceLabels = { low: 'Baixa', medium: 'Média', high: 'Alta' };

function appendReportField(container, label, value) {
    const values = Array.isArray(value)
        ? value.filter((item) => typeof item === 'string' && item.trim())
        : typeof value === 'string' && value.trim() ? [value] : [];
    if (!values.length) return;

    const field = document.createElement('div');
    field.className = 'detail-field';
    const heading = document.createElement('strong');
    heading.textContent = label;
    field.append(heading);

    if (Array.isArray(value)) {
        const list = document.createElement('ul');
        for (const entry of values) {
            const item = document.createElement('li');
            item.textContent = entry;
            list.append(item);
        }
        field.append(list);
    } else {
        const text = document.createElement('p');
        text.textContent = value;
        field.append(text);
    }
    container.append(field);
}

function appendStructuredItems(containerId, values, kind, emptyText) {
    const container = document.getElementById(containerId);
    container.replaceChildren();
    const items = Array.isArray(values) ? values : [];
    if (!items.length) {
        const empty = document.createElement('p');
        empty.className = 'empty-detail';
        empty.textContent = emptyText;
        container.append(empty);
        return;
    }

    for (const value of items) {
        const entry = typeof value === 'string' ? { pattern: value, focus: value } : value;
        if (!entry || typeof entry !== 'object') continue;

        const item = document.createElement('article');
        item.className = `detail-item ${kind}-item`;
        const heading = document.createElement('div');
        heading.className = 'detail-item-heading';
        const title = document.createElement('h3');
        title.textContent = entry.pattern || entry.focus || entry.original || 'Observação da sessão';
        heading.append(title);

        if (Number.isFinite(Number(entry.frequency)) && Number(entry.frequency) > 0) {
            const frequency = document.createElement('span');
            frequency.className = 'frequency-tag';
            frequency.textContent = `${entry.frequency} ${Number(entry.frequency) === 1 ? 'ocorrência' : 'ocorrências'}`;
            heading.append(frequency);
        }

        if (entry.confidence) {
            const confidence = document.createElement('span');
            confidence.className = `confidence-tag confidence-${entry.confidence}`;
            confidence.textContent = `Confiança ${confidenceLabels[entry.confidence] || 'Baixa'}`;
            heading.append(confidence);
        }
        item.append(heading);

        if (kind === 'improvement' && entry.priority) {
            const priority = document.createElement('p');
            priority.className = 'priority-tag';
            priority.textContent = `Prioridade ${entry.priority}`;
            item.append(priority);
        }

        appendReportField(item, kind === 'strength' ? 'Evidência' : 'Exemplos observados', entry.evidence);
        appendReportField(item, 'Por que importa', entry.why_it_matters || entry.impact || entry.why);
        appendReportField(item, 'Exercício', entry.exercise);
        appendReportField(item, 'Exemplo para praticar', entry.example);
        appendReportField(item, 'Meta', entry.goal);
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
        explanation.textContent = fields.explanation(entry) || '';
        item.append(originalLabel, original, suggestion, explanation);
        appendReportField(item, 'Categoria', entry.category);
        appendReportField(item, 'Importância', entry.importance);
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
        const metric = metrics[key] && typeof metrics[key] === 'object' ? metrics[key] : { score: metrics[key] };
        const score = Math.max(0, Math.min(100, Number(metric.score) || 0));
        const row = document.createElement('div');
        row.className = 'metric-row';
        const name = document.createElement('span');
        name.className = 'metric-name';
        name.textContent = label;
        const track = document.createElement('span');
        track.className = 'metric-track';
        track.setAttribute('role', 'img');
        track.setAttribute('aria-label', label);
        const marker = document.createElement('span');
        marker.className = 'metric-marker';
        marker.style.left = `${score}%`;
        track.append(marker);
        const scoreText = document.createElement('span');
        scoreText.className = 'metric-score';
        scoreText.textContent = `${score}/100`;
        row.append(name, track, scoreText);

        const support = document.createElement('div');
        support.className = 'metric-support';
        const evidence = document.createElement('p');
        evidence.textContent = metric.evidence || 'Evidência textual insuficiente para esta dimensão.';
        const confidence = document.createElement('span');
        confidence.className = `confidence-tag confidence-${metric.confidence || 'low'}`;
        confidence.textContent = `Confiança ${confidenceLabels[metric.confidence] || 'Baixa'}`;
        support.append(evidence, confidence);
        row.append(support);
        chart.append(row);
    }

    appendStructuredItems('strengths-list', report.strengths, 'strength', 'Sem evidências suficientes para identificar pontos fortes nesta sessão.');
    appendStructuredItems('weaknesses-list', report.weaknesses, 'weakness', 'Nenhum padrão de atenção sustentado pelas falas foi identificado.');
    appendStructuredItems('improvements-list', report.improvements, 'improvement', 'Não há exercícios específicos para esta sessão.');
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

    const transcriptionNotes = Array.isArray(report.transcription_notes) ? report.transcription_notes : [];
    document.getElementById('transcription-notes-section').hidden = !transcriptionNotes.length;
    appendStructuredItems(
        'transcription-notes-list',
        transcriptionNotes.map((note) => ({
            pattern: note.transcript_text,
            evidence: note.possible_phrase ? [`Possível frase: ${note.possible_phrase}`] : [],
            impact: note.reason,
            goal: note.next_step
        })),
        'transcription',
        ''
    );

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

document.getElementById('save-html').addEventListener('click', exportHtml);
document.getElementById('back-button').addEventListener('click', () => window.learningReport.back());
document.getElementById('quit-button').addEventListener('click', () => window.learningReport.quit());

if (window.learningReport) {
    window.learningReport.onData(renderReport);
} else {
    loadingOverlay.hidden = true;
    reportNotice.hidden = false;
    reportNotice.textContent = 'Abra esta página pelo aplicativo Live Room para carregar um relatório.';
}

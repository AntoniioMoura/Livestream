const feed = document.getElementById('teacher-feed');
const shell = document.querySelector('.teacher-shell');
let latestFeedbackId = null;
let latestCard = null;

function createCard({ id, original, pending = false }) {
    feed.replaceChildren();

    const card = document.createElement('div');
    card.className = `teacher-bubble${pending ? ' teacher-pending' : ''}`;
    card.dataset.feedbackId = id;

    const originalText = document.createElement('p');
    originalText.className = 'teacher-original';
    originalText.textContent = pending ? 'Analisando sua frase…' : original;
    card.append(originalText);
    feed.append(card);
    latestCard = card;
    return card;
}

function handleFeedback(event) {
    if (event.id !== latestFeedbackId) return;
    const card = latestCard || createCard(event);
    card.classList.remove('teacher-pending', 'teacher-error');
    card.replaceChildren();

    if (event.tipo === 'teacher_error') {
        const explanation = document.createElement('p');
        explanation.className = 'teacher-explanation';
        explanation.textContent = event.mensagem;
        card.append(explanation);
    } else {
        const original = document.createElement('p');
        original.className = 'teacher-original';
        original.textContent = event.original;

        const correction = document.createElement('p');
        correction.className = 'teacher-correction';
        correction.textContent = event.correcao;

        const explanation = document.createElement('p');
        explanation.className = 'teacher-explanation';
        explanation.textContent = event.explicacao;
        card.append(original, correction, explanation);
    }
}

window.liveChat?.onEvent((event) => {
    if (event.tipo === 'teacher_pending') {
        latestFeedbackId = event.id;
        createCard({ ...event, pending: true });
    } else if (event.tipo === 'teacher_feedback' || event.tipo === 'teacher_error') {
        handleFeedback(event);
    } else if (event.tipo === 'teacher_move_mode') {
        shell.classList.toggle('is-movable', event.enabled);
    }
});
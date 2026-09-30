const messageList = document.getElementById('message-list');
const botMessageQueue = [];
const notificationSound = new Audio('./pop.mp3');
notificationSound.preload = 'auto';
let isShowingBotMessage = false;

const botColors = {
    Jake: 'jake',
    Lulu_Cat: 'lulu',
    kevin_noob: 'kevin',
    Lord_meme: 'lord'
};

// Adicionamos o "traducao" na lista de propriedades desempacotadas
function addBubble({ nome = 'Sistema', mensagem = '', tipo = 'bot', tipo_mensagem, traducao }) {
    console.log(`[Tradutor-Log] 3. Front-end recebeu -> Bot: ${nome} | Tradução: ${traducao}`);
    const bubble = document.createElement('li');
    const color = botColors[nome];
    bubble.className = `chat-bubble ${tipo === 'error' ? 'system-bubble' : tipo === 'notice' ? 'notice-bubble' : (color || 'default-bubble')}`;
    if (tipo !== 'error') {
        const username = document.createElement('strong');
        username.className = 'bubble-name';
        username.textContent = nome;
        bubble.append(username);
    }

    const text = document.createElement('p');
    text.className = 'bubble-text';
    text.textContent = mensagem;

    // Usamos a propriedade "traducao" diretamente em vez do "event.traducao"
    if (traducao) {
        const translationSpan = document.createElement('span');
        translationSpan.className = 'bubble-translation';
        translationSpan.textContent = ` - (${traducao})`;
        text.appendChild(translationSpan);
    }

    bubble.append(text);
    messageList.append(bubble);

    if (tipo_mensagem === 'bot' || tipo === 'bot') {
        notificationSound.currentTime = 0;
        notificationSound.play().catch((error) => {
            console.error('[notification-sound] Could not play pop.mp3:', error);
        });
    }

    if (tipo !== 'notice') {
        messageList.querySelector('.notice-bubble')?.remove();
    }

    while (messageList.children.length > 8) {
        messageList.firstElementChild.remove();
    }
    messageList.scrollTop = messageList.scrollHeight;
    requestAnimationFrame(() => window.liveChat?.acknowledgeRender());
}

function showNextBotMessage() {
    const nextMessage = botMessageQueue.shift();
    if (!nextMessage) {
        isShowingBotMessage = false;
        return;
    }

    addBubble(nextMessage);
    window.setTimeout(showNextBotMessage, 2000);
}

if (window.liveChat) {
    window.liveChat.onEvent((event) => {
        if (event.tipo === 'message') {
            if (event.tipo_mensagem === 'bot' && event.nome !== 'System') {
                botMessageQueue.push(event);
                if (!isShowingBotMessage) {
                    isShowingBotMessage = true;
                    showNextBotMessage();
                }
            } else if (event.nome === 'System') {
                addBubble({ mensagem: event.mensagem, tipo: 'error' });
            }
        } else if (event.tipo === 'status' && event.status === 'live') {
            addBubble({ mensagem: 'Chat conectado · aguardando mensagens', tipo: 'notice' });
        } else if (event.tipo === 'error') {
            addBubble({ mensagem: event.mensagem, tipo: 'error' });
        }

    });
}
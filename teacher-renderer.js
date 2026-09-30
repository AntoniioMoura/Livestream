const feed = document.getElementById('teacher-feed');

if (window.liveChat) {
    window.liveChat.onEvent((event) => {
        
        // 1. Só faz algo quando chegar uma correção real
        if (event.tipo === 'teacher_feedback') {
            
            // Limpa qualquer bolha antiga que estiver na tela
            feed.innerHTML = ''; 

            const bubble = document.createElement('div');
            bubble.className = 'teacher-bubble';
            bubble.id = `teacher-msg-${event.id}`;

            const original = document.createElement('p');
            original.className = 'teacher-original';
            original.textContent = `"${event.original}"`;

            const correction = document.createElement('p');
            correction.className = 'teacher-correction';
            correction.textContent = event.correcao;

            const explanation = document.createElement('p');
            explanation.className = 'teacher-explanation';
            explanation.textContent = event.explicacao;

            bubble.appendChild(original);
            bubble.appendChild(correction);
            bubble.appendChild(explanation);

            feed.appendChild(bubble);
            
            // Note que NÃO há temporizador (setTimeout) aqui.
            // A bolha vai ficar presa na tela infinitamente até o próximo erro.
        }

        // 2. Controle para permitir arrastar a janela (Ctrl+Shift+F12)
        if (event.tipo === 'teacher_move_mode') {
            const shell = document.querySelector('.teacher-shell');
            if (shell) {
                shell.classList.toggle('is-movable', event.enabled);
            }
        }
    });
}
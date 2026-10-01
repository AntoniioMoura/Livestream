import json
import time
import random
import os
import sys
import re
import threading
from datetime import datetime
from pathlib import Path
import speech_recognition as sr
import base64
import io
from concurrent.futures import ThreadPoolExecutor
import mss
import requests
from PIL import Image

MAX_WORLDBUILDING_PROMPT_CHARS = 1800
MODELO_VISAO = "minicpm-v"

def emitir_evento(tipo, **dados):
    print(json.dumps({"tipo": tipo, **dados}, ensure_ascii=False), flush=True)

def emitir_log(mensagem):
    print(mensagem, file=sys.stderr, flush=True)


def salvar_historico(historico):
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historico_live.txt")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(historico))

def carregar_configuracao():
    try:
        indice = sys.argv.index("--config-json")
        valores = json.loads(sys.argv[indice + 1])
    except (ValueError, IndexError, json.JSONDecodeError):
        valores = {}

    if not isinstance(valores, dict):
        valores = {}

    nome_streamer = valores.get("streamerName", "")
    if not isinstance(nome_streamer, str):
        nome_streamer = ""

    idioma = valores.get("language", "en")
    complexidade = valores.get("complexity", "normal")
    respostas = valores.get("responseCount", "random")

    try:
        intervalo = int(valores.get("silenceInterval", 25))
    except (TypeError, ValueError):
        intervalo = 25

    if idioma not in {"en", "pt"}:
        idioma = "en"
    if complexidade not in {"simple", "normal", "advanced"}:
        complexidade = "normal"
    if str(respostas) not in {"1", "2", "3", "random"}:
        respostas = "random"

    personalidades_recebidas = valores.get("personas", {})
    if not isinstance(personalidades_recebidas, dict):
        personalidades_recebidas = {}

    personalidades = {}
    for nome, descricao_padrao in PERSONALIDADES_PADRAO.items():
        descricao = personalidades_recebidas.get(nome, descricao_padrao)
        if not isinstance(descricao, str) or not descricao.strip():
            descricao = descricao_padrao
        personalidades[nome] = descricao.strip()[:180]

    return {
        "theme": str(valores.get("theme", "Gameplay e conversa com o chat")).strip()[:120]
        or "Gameplay e conversa com o chat",
        "streamer_name": " ".join(nome_streamer.split())[:40],
        "language": idioma,
        "complexity": complexidade,
        "response_count": str(respostas),
        "silence_chat": bool(valores.get("silenceChat", True)),
        "silence_interval": max(10, min(60, intervalo)),
        "personas": personalidades,
        "worldbuilding_file": str(valores.get("worldbuildingFile", "")).strip(),
        "use_translator": bool(valores.get("useTranslator", False)),
    }


def quantidade_de_respostas(configuracao, silencioso=False):
    quantidade = configuracao["response_count"]
    if quantidade == "random":
        return random.randint(1, 2) if silencioso else random.randint(1, 3)
    return int(quantidade)


def calcular_intervalo_silencio(configuracao):
    intervalo = configuracao["silence_interval"]
    return random.uniform(max(5, intervalo - 5), intervalo + 5)


PERSONALIDADES_PADRAO = {
    "Jake": "Hypes up good moves, talks about game strategies and their own gaming experiences.",
    "Lulu_Cat": "Sweet and supportive; asks personal questions and sends positive vibes.",
    "kevin_noob": "A curious fan who asks genuine questions about the game and the conversation.",
    "Lord_meme": "Playfully teases, makes jokes and uses emotes, while always staying friendly.",
}


def _normalizar_mensagem_chat(mensagem):
    texto = re.sub(r"[^\w\s]", " ", mensagem.casefold(), flags=re.UNICODE)
    return " ".join(texto.split())


def _fala_aciona_analise_visual(fala):
    texto = " ".join(fala.casefold().split())
    padroes = (
        r"\b(?:look|watch)\b",
        r"\b(?:look|check)\s+(?:at\s+)?(?:this|that|here)\b",
        r"\b(?:can|could|do)\s+you\s+see\b",
        r"\b(?:what(?:'s|\s+is)|who(?:'s|\s+is))\s+(?:this|that|it)\b",
        r"\b(?:olha|veja|repara)\b",
        r"\b(?:o que é|quem é)\s+(?:isso|aquilo|esse|essa)\b",
    )
    return any(re.search(padrao, texto) for padrao in padroes)


def _mensagem_ja_usada_recentemente(mensagem, historico_da_live):
    mensagem_normalizada = _normalizar_mensagem_chat(mensagem)
    if not mensagem_normalizada:
        return False

    for linha in historico_da_live[-12:]:
        nome, separador, mensagem_anterior = linha.partition(": ")
        if separador and nome in PERSONALIDADES_PADRAO:
            if _normalizar_mensagem_chat(mensagem_anterior) == mensagem_normalizada:
                return True
    return False


def chamar_ia_bot(
    fala_do_streamer,
    historico_da_live,
    bots_excluidos=None,
    configuracao=None,
    mensagem_rejeitada=None,
    contexto_visual=None,
    pergunta_streamer=None,
    persona_forcada=None # ADICIONADO: Parâmetro para forçar quem foi chamado
):
    configuracao = configuracao or carregar_configuracao()
    ultimas_mensagens = historico_da_live[-20:] if len(historico_da_live) > 0 else ["Chat is empty."]
    contexto_chat = "\n".join(ultimas_mensagens)
    
    if fala_do_streamer == "visual_reaction":
        evento = f"A new screenshot analysis is ready: {json.dumps(contexto_visual, ensure_ascii=False)}"
        if pergunta_streamer:
            evento += f" The streamer asked: {json.dumps(pergunta_streamer, ensure_ascii=False)}"
    elif fala_do_streamer == "chain_reaction":
        if contexto_visual:
            evento = (
                "Another viewer just reacted to the latest screenshot. Respond to their message "
                f"while staying on this visual context: {json.dumps(contexto_visual, ensure_ascii=False)}"
            )
        else:
            evento = "Another viewer just sent a message. React to it! Agree, laugh, or add to the hype."
    elif fala_do_streamer:
        evento = f"Streamer just said: {json.dumps(fala_do_streamer, ensure_ascii=False)}"
    else:
        evento = "Idle chat. Ask a casual question, greet the streamer, or talk about the vibe."

    # 1. LÓGICA DE FORÇAR A PERSONA MENCIONADA
    personas_disponiveis = configuracao['personas'].copy()
    if persona_forcada and persona_forcada in personas_disponiveis:
        # Se o streamer chamou alguém, APENAS ele pode responder
        personas_disponiveis = {persona_forcada: personas_disponiveis[persona_forcada]}
    else:
        if bots_excluidos:
            for bot_ignorado in bots_excluidos:
                personas_disponiveis.pop(bot_ignorado, None)
        if not personas_disponiveis:
            personas_disponiveis = configuracao['personas']
            
    lista_personas = "\n".join([f'- "{nome}": {desc}' for nome, desc in personas_disponiveis.items()])

    # 2. DEFINIÇÃO DA TRADUÇÃO E JSON
    if configuracao.get("use_translator") and configuracao["language"] == "en":
        regra_traducao = "15. TRANSLATION: You MUST translate your message to Brazilian Portuguese and put it in the 'traducao' key."
        exemplo_json = '{"nome": "Jake", "mensagem": "English text here", "traducao": "Texto em pt-br aqui"}'
    else:
        regra_traducao = ""
        exemplo_json = '{"nome": "Jake", "mensagem": "Text here"}'

    # 3. REGRAS ATUALIZADAS (Foco na Regra 7 para barrar invenções)
    complexidade = {
        "simple": "Use familiar words, simple ideas, and short direct reactions.",
        "normal": "Use casual gamer language and keep the reaction direct.",
        "advanced": "Use a precise gaming term when useful, but keep the reaction just as brief and conversational.",
    }[configuracao["complexity"]]
    
    idioma = "Brazilian Portuguese" if configuracao["language"] == "pt" else "English"
    limite_palavras = {"simple": 6, "normal": 8, "advanced": 10}[configuracao["complexity"]]
    nome_streamer = configuracao["streamer_name"]
    instrucao_nome_streamer = f'The streamer goes by "{nome_streamer}".' if nome_streamer else "No streamer name."
    instrucao_visual = "VISUAL GROUP: Focus strictly on the screenshot context provided." if contexto_visual else ""

    system_prompt = f"""
    You are simulating a Twitch chat for a friendly gaming stream. 
    
    STRICT RULES:
     1. LENGTH: 1 to {limite_palavras} words MAXIMUM.
     2. ONE THOUGHT: Write one brief reaction or short question.
     3. CHAT STYLE: Sound like a viewer typing quickly on a keyboard.
     4. ANTI-ECHO: Read the Recent Chat History. NEVER repeat what was already said.
     5. DIRECT REPLY: If a streamer message is provided, reply to it directly.
     6. GREETINGS: If the streamer greets you, greet them back.
     7. GROUNDED CONVERSATION (CRITICAL): Do NOT invent in-game events (like 'epic kill', 'I see a dragon') unless reacting to a Visual Context or a specific game event mentioned by the streamer. For idle chat, stick to generic topics (asking how the streamer is, stream quality, saying hi, etc.).
     8. NO INVENTED STORIES: Never claim you are playing the game yourself.
     9. STREAMER NAME: {instrucao_nome_streamer}
     10. DIRECT ADDRESS: If the streamer calls your persona by name, you must reply.
     11. EMOTES: Occasionally use one Twitch emote.
     12. TOPIC: Stay relevant to the theme: {configuracao['theme']}.
     13. LANGUAGE: Write 'mensagem' EXCLUSIVELY in {idioma}.
     14. COMPLEXITY: {complexidade}
     {regra_traducao}
    {instrucao_visual}
    
    Choose ONE persona from this list below and follow its behavior strictly:
    {lista_personas}

    Recent Chat History:
    {contexto_chat}
    
    Current Event:
    {evento}
    
    Return ONLY a valid JSON object matching this EXACT format:
    {exemplo_json}
    """
    
    user_content = "Generate one brief message that fits the ongoing game or chat conversation."
    if fala_do_streamer == "visual_reaction":
        user_content = f"React to this screenshot analysis: {json.dumps(contexto_visual, ensure_ascii=False)}"
        if pergunta_streamer:
            user_content += f" The streamer asked: {json.dumps(pergunta_streamer, ensure_ascii=False)}"
    elif fala_do_streamer == "chain_reaction":
        user_content = "React to the latest chat message naturally to create a herd effect."
        if contexto_visual:
            user_content += f" Keep your reaction on this screenshot: {json.dumps(contexto_visual, ensure_ascii=False)}"
    elif fala_do_streamer:
        user_content = f"Reply directly to the streamer's latest message: {json.dumps(fala_do_streamer, ensure_ascii=False)}"
        
    if mensagem_rejeitada:
        user_content += (
            f" WARNING: Your previous draft '{mensagem_rejeitada}' was rejected. "
            "You MUST write something COMPLETELY DIFFERENT now and ensure you picked an allowed persona."
        )

    try:
        payload = {
            "model": "llama3.1",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "format": "json", 
            "stream": False,
            "options": {
                "temperature": 0.8,
                "num_predict": 60
            }
        }
        
        resposta = requests.post("http://localhost:11434/api/chat", json=payload, timeout=20)
        resposta.raise_for_status()
        
        dados_json = resposta.json()
        texto_resposta = dados_json["message"]["content"].strip()
        resposta_json = json.loads(texto_resposta)
        
        return (
            resposta_json.get("nome", "Viewer"), 
            resposta_json.get("mensagem", "..."),
            resposta_json.get("traducao", None)
        )
    except Exception as e:
        emitir_log(f"Erro ao gerar mensagem no Ollama: {e}")
        return None


def avaliar_fala_professor(fala, configuracao):
    emitir_log(f"\n[Professor-Log] 1. Iniciando análise para: '{fala}'")
    idioma_alvo = "English" if configuracao["language"] == "en" else "Brazilian Portuguese"
    
    prompt_sistema = f"""You are a practical {idioma_alvo} language teacher for a Twitch gaming livestream.
Review the learner's speech transcription. 
CRITICAL RULES:
1. ONLY correct genuine grammatical errors (e.g., wrong verb tense, subject-verb agreement, missing prepositions).
2. NEVER correct informality, slang, or gamer culture words (e.g., "guys", "bro", "gonna", "wanna", "dude"). Twitch chats are inherently informal.
3. IGNORE stylistic choices. If the grammar is correct, DO NOT suggest "better", "more natural", or "more formal" ways to say it.
4. IGNORE punctuation, capitalization, and comma placement completely.
5. EXPLANATION MUST BE EXTREMELY SHORT AND DIRECT: Maximum 1 short sentence. No complex grammar jargon.
If no significant grammatical error exists, you MUST return empty strings for "correcao" and "explicacao".
Return ONLY valid JSON with keys "correcao" and "explicacao".
Explain in Brazilian Portuguese."""

    payload = {
        "model": "llama3.1",
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Learner's sentence: {json.dumps(fala, ensure_ascii=False)}"},
        ],
        "format": "json",
        "stream": False,
        # Aumentamos para 300 para garantir que o JSON nunca seja cortado no meio
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    
    try:
        emitir_log("[Professor-Log] 2. Aguardando resposta do Ollama...")
        resposta = requests.post("http://localhost:11434/api/chat", json=payload, timeout=45)
        resposta.raise_for_status()
        dados_json = resposta.json()
        resposta_bruta = dados_json["message"]["content"].strip()
        emitir_log(f"[Professor-Log] 3. Retorno bruto: {resposta_bruta}")
        
        resultado = json.loads(resposta_bruta)
    except Exception as e:
        emitir_log(f"[Professor-Log] ❌ Erro ao consultar a IA: {e}")
        return {"status": "erro"}

    correcao = resultado.get("correcao", "")
    explicacao = resultado.get("explicacao", "")
    
    if not isinstance(correcao, str) or not correcao.strip() or not explicacao.strip():
        emitir_log("[Professor-Log] 4. Sem erro gramatical. Ignorando.")
        return {"status": "ignorar"}
        
    fala_limpa = re.sub(r'[^\w\s]', '', fala.casefold()).strip()
    correcao_limpa = re.sub(r'[^\w\s]', '', correcao.casefold()).strip()
    
    if fala_limpa == correcao_limpa:
        emitir_log("[Professor-Log] 4. Mudança apenas de pontuação. Ignorando.")
        return {"status": "ignorar"}
        
    emitir_log("[Professor-Log] 4. Correção validada!")
    return {"status": "corrigir", "correcao": correcao.strip()[:500], "explicacao": explicacao.strip()[:700]}


def caminho_historico_professor():
    return Path(__file__).resolve().parent / "historico_professor.json"


def _carregar_sessoes_professor():
    caminho = caminho_historico_professor()
    if caminho.exists():
        try:
            sessoes = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError("O histórico do professor não pôde ser lido; ele foi preservado.") from e
        if not isinstance(sessoes, list):
            raise RuntimeError("O histórico do professor não contém um array de sessões.")
        return sessoes

    caminho_legado = caminho.with_name("historico_professor.jsonl")
    registros_legados = []
    if caminho_legado.exists():
        with caminho_legado.open("r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                try:
                    registro = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if isinstance(registro, dict):
                    registros_legados.append(registro)

    if registros_legados:
        return [{
            "id": "sessao-legada",
            "started_at": "",
            "interactions": registros_legados,
        }]
    return []


def _gravar_sessoes_professor(sessoes):
    caminho = caminho_historico_professor()
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(
        json.dumps(sessoes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)


def iniciar_sessao_historico_professor():
    sessoes = _carregar_sessoes_professor()
    identificador = str(time.time_ns())
    sessoes.append({
        "id": identificador,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "interactions": [],
    })
    _gravar_sessoes_professor(sessoes)
    return identificador


def salvar_historico_professor(identificador_sessao, registro):
    sessoes = _carregar_sessoes_professor()
    sessao = next((item for item in reversed(sessoes) if item.get("id") == identificador_sessao), None)
    if sessao is None:
        raise RuntimeError("A sessão atual não foi encontrada no histórico do professor.")
    sessao.setdefault("interactions", []).append(registro)
    _gravar_sessoes_professor(sessoes)


def carregar_documento_worldbuilding(nome_arquivo):
    if not nome_arquivo:
        return ""

    caminho = Path(nome_arquivo)
    if caminho.name != nome_arquivo or caminho.suffix.lower() not in {".md", ".markdown", ".txt", ".json"}:
        emitir_log("Documento de worldbuilding ignorado: nome ou extensão inválidos.")
        return ""

    caminho_completo = Path(__file__).resolve().parent / "worldbuilding" / caminho.name
    try:
        return caminho_completo.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError) as e:
        emitir_log(f"Não foi possível carregar o documento de worldbuilding {caminho.name!r}: {e}")
        return ""


def selecionar_contexto_worldbuilding(documento, limite=MAX_WORLDBUILDING_PROMPT_CHARS):
    if not documento:
        return ""
    
    documento_limpo = documento.strip()
    return documento_limpo[:limite]


def iniciar_live():
    configuracao = carregar_configuracao()
    evento_parada = threading.Event()
    threading.Thread(
        args=(evento_parada,),
        daemon=True,
    ).start()
    documento_worldbuilding = carregar_documento_worldbuilding(configuracao["worldbuilding_file"])
    nome_jogo_worldbuilding = Path(configuracao["worldbuilding_file"]).stem
    
    if documento_worldbuilding:
        emitir_log(
            f"Worldbuilding carregado em memória: {configuracao['worldbuilding_file']} "
            f"({len(documento_worldbuilding)} caracteres)."
        )
        if len(documento_worldbuilding) > MAX_WORLDBUILDING_PROMPT_CHARS:
            emitir_log(
                f"O documento será limitado a "
                f"{MAX_WORLDBUILDING_PROMPT_CHARS} caracteres por análise."
            )

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.5
    microphone = sr.Microphone()
    historico_da_live = []
    identificador_sessao_professor = iniciar_sessao_historico_professor()
    executor_professor = ThreadPoolExecutor(max_workers=1)
    
    # 1. Cooldown Global (Fila que lembra os últimos bots)
    fila_de_cooldown_bots = []
    
    executor_visual = ThreadPoolExecutor(max_workers=1)
    futuro_analise_visual = None
    fala_visual_pendente = None
    resposta_ociosa_pendente = False

    def emitir_respostas(foco, silencioso=False, contexto_visual=None, pergunta_streamer=None):
        grupo_visual = contexto_visual is not None
        quantidade = random.randint(2, 4) if grupo_visual else quantidade_de_respostas(
            configuracao,
            silencioso=silencioso,
        )
        bots_da_rodada = []
        
        # LÓGICA DE DIRECIONAMENTO DE RESPOSTA
        persona_mencionada = None
        if foco and isinstance(foco, str) and foco not in ["visual_reaction", "chain_reaction"]:
            texto_foco = foco.lower()
            
            # 1. Prioridade Máxima: O streamer chamou alguém pelo nome?
            for nome_bot_cfg in configuracao['personas'].keys():
                nome_simples = nome_bot_cfg.split('_')[0].lower() # Pega "kevin" de "kevin_noob"
                if re.search(rf"\b{nome_simples}\b", texto_foco) or nome_bot_cfg.lower() in texto_foco:
                    persona_mencionada = nome_bot_cfg
                    break
            
            # 2. Contexto Contínuo: O streamer está respondendo a uma pergunta recente?
            if not persona_mencionada and historico_da_live:
                # Pega as últimas 3 mensagens e inverte (olha da mais recente para a mais antiga)
                ultimas_mensagens = reversed(historico_da_live[-3:])
                
                for linha in ultimas_mensagens:
                    if "?" in linha:
                        # Achou uma pergunta! Vamos identificar quem foi o autor
                        for nome_bot_cfg in configuracao['personas'].keys():
                            if linha.startswith(f"{nome_bot_cfg}:"):
                                persona_mencionada = nome_bot_cfg
                                emitir_log(f"Contexto Ativo: Retomando diálogo com {persona_mencionada} após pergunta recente.")
                                break
                    
                    # Se já encontrou a persona que fez a pergunta, para de procurar nas outras linhas
                    if persona_mencionada:
                        break

        for indice in range(quantidade):
            if evento_parada.is_set():
                break
            # ... (MANTENHA O RESTANTE DO LOOP INTACTO DAQUI PARA BAIXO) ...
                break
            if indice > 0:
                time.sleep(random.uniform(0.5, 1.5))
            
            foco_atual = foco if indice == 0 else "chain_reaction"
            if grupo_visual:
                foco_atual = "visual_reaction" if indice == 0 else "chain_reaction"

            bots_excluidos_agora = list(set(bots_da_rodada + fila_de_cooldown_bots))
            
            # Se alguém foi mencionado, tira ele do castigo para poder responder!
            if persona_mencionada and persona_mencionada in bots_excluidos_agora:
                bots_excluidos_agora.remove(persona_mencionada)
            
            mensagem_rejeitada = None
            resposta = None
            
            for tentativa in range(3): 
                resposta = chamar_ia_bot(
                    foco_atual,
                    historico_da_live,
                    bots_excluidos_agora,
                    configuracao,
                    mensagem_rejeitada=mensagem_rejeitada,
                    contexto_visual=contexto_visual,
                    pergunta_streamer=pergunta_streamer if grupo_visual else None,
                    # Força a IA a usar a persona mencionada apenas na primeira resposta
                    persona_forcada=persona_mencionada if indice == 0 else None
                )

                if resposta is None:
                    break

                nome_bot, mensagem, traducao = resposta
                
                # BARREIRA CONTRA ALUCINAÇÃO DE BOT (Adeus, Sly_Ninja)
                if nome_bot not in configuracao['personas']:
                    emitir_log(f"Rejeitado: IA inventou o bot '{nome_bot}'.")
                    mensagem_rejeitada = mensagem
                    continue
                
                persona_repetida = nome_bot in bots_excluidos_agora
                mensagem_repetida = _mensagem_ja_usada_recentemente(mensagem, historico_da_live)
                
                if not persona_repetida and not mensagem_repetida:
                    break 

                emitir_log(f"Rejeitado: Bot {nome_bot} (Repetido: {persona_repetida}) | Msg (Repetida: {mensagem_repetida})")
                mensagem_rejeitada = mensagem
            else:
                emitir_log("Resposta descartada após 3 tentativas de repetição ou alucinação.")
                continue
            
            if resposta is None:
                emitir_evento("error", mensagem="Erro de comunicação com o Ollama.")
                break

            historico_da_live.append(f"{nome_bot}: {mensagem}")
            salvar_historico(historico_da_live)
            emitir_evento("message", tipo_mensagem="bot", nome=nome_bot, mensagem=mensagem, traducao=traducao)
            
            bots_da_rodada.append(nome_bot)
            fila_de_cooldown_bots.append(nome_bot)
            if len(fila_de_cooldown_bots) > 2:
                fila_de_cooldown_bots.pop(0)

    def solicitar_feedback_professor(fala):
        identificador = str(time.time_ns())
        
        # O "Analisando..." aparece na tela
        emitir_evento("teacher_pending", id=identificador, original=fala)
        
        tarefa = executor_professor.submit(avaliar_fala_professor, fala, configuracao)

        def publicar_feedback(resultado):
            try:
                feedback = resultado.result()
                emitir_log(f"[Professor-Log] 5. Callback recebido com status: {feedback.get('status')}")
                
                if feedback.get("status") == "ignorar":
                    # Manda o Front-end apagar a bolha de "Analisando..." pois não há erro
                    emitir_evento("teacher_dismiss", id=identificador)
                    return
                    
                if feedback.get("status") == "erro":
                    emitir_evento("teacher_error", id=identificador, original=fala, mensagem="Falha na análise.")
                    return

                # Se chegou aqui, temos uma correção útil para exibir
                registro = {
                    "id": identificador,
                    "original": fala,
                    "correcao": feedback["correcao"],
                    "explicacao": feedback["explicacao"]
                }
                salvar_historico_professor(identificador_sessao_professor, registro)
                emitir_evento("teacher_feedback", **registro)
                
            except Exception as erro:
                emitir_log(f"[Professor-Log] ❌ Erro fatal no callback: {erro}")
                emitir_evento("teacher_error", id=identificador, original=fala, mensagem="Erro interno.")

        tarefa.add_done_callback(publicar_feedback)

    def agendar_analise_visual(fala=None, aguardar_resposta=False):
        nonlocal futuro_analise_visual, fala_visual_pendente, resposta_ociosa_pendente

        if futuro_analise_visual is not None:
            emitir_log("Diretor de Visão: análise anterior ainda está em andamento; novo print ignorado.")
            return aguardar_resposta and not fala and resposta_ociosa_pendente

        futuro_analise_visual = executor_visual.submit(
            capturar_e_analisar_tela,
            fala,
            configuracao["theme"],
            documento_worldbuilding,
            nome_jogo_worldbuilding,
        )
        fala_visual_pendente = fala if aguardar_resposta and fala else None
        resposta_ociosa_pendente = aguardar_resposta and not fala
        return True

    def concluir_analise_visual():
        nonlocal futuro_analise_visual, fala_visual_pendente, resposta_ociosa_pendente

        if futuro_analise_visual is None or not futuro_analise_visual.done():
            return

        try:
            descricao_tela = futuro_analise_visual.result()
        except Exception as e:
            emitir_log(f"Erro na tarefa de análise visual: {e}")
            descricao_tela = None

        frase_pendente = fala_visual_pendente
        responder_apos_analise = resposta_ociosa_pendente
        futuro_analise_visual = None
        fala_visual_pendente = None
        resposta_ociosa_pendente = False

        if descricao_tela:
            historico_da_live.append(f"[Visual Context: {descricao_tela}]")
            salvar_historico(historico_da_live)

        if descricao_tela:
            emitir_respostas(
                "visual_reaction",
                contexto_visual=descricao_tela,
                pergunta_streamer=frase_pendente,
            )
        elif frase_pendente:
            emitir_respostas(frase_pendente)
        elif responder_apos_analise:
            emitir_respostas(None, silencioso=True)

    try:
        with microphone as source:
            emitir_log("Ajustando ruído de fundo...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            # Avisa na interface que está gravando
            emitir_evento("status", status="live", mensagem="Live ON: Microfone ativo!")

            ultimo_momento_interacao = time.time()
            proximo_intervalo_silencio = calcular_intervalo_silencio(configuracao)

            while True:
                concluir_analise_visual()

                try:
                    inicio_escuta = time.perf_counter()
                    audio = recognizer.listen(source, timeout=2, phrase_time_limit=15)
                    emitir_log(f"Áudio capturado em {time.perf_counter() - inicio_escuta:.2f}s.")
                    emitir_log("Transcrevendo com Whisper...")
                    
                    idioma_whisper = "portuguese" if configuracao["language"] == "pt" else "english"
                    inicio_transcricao = time.perf_counter()
                    fala_usuario = recognizer.recognize_whisper(audio, language=idioma_whisper).strip()
                    emitir_log(f"Whisper concluiu em {time.perf_counter() - inicio_transcricao:.2f}s.")
                    
                except sr.WaitTimeoutError:
                    fala_usuario = None
                except Exception:
                    fala_usuario = None

                # ==========================================
                # 1. STREAMER FALOU
                # ==========================================
                if fala_usuario and len(fala_usuario) > 3:
                    resposta_ociosa_pendente = False
                    historico_da_live.append(f"Streamer: {fala_usuario}")
                    salvar_historico(historico_da_live)
                    
                    emitir_evento("message", tipo_mensagem="streamer", nome="Você", mensagem=fala_usuario)
                    
                    # GATILHO VISUAL POR VOZ
                    if _fala_aciona_analise_visual(fala_usuario):
                        if not agendar_analise_visual(fala_usuario, aguardar_resposta=True):
                            emitir_respostas(fala_usuario)
                    else:
                        emitir_respostas(fala_usuario)
                    
                    ultimo_momento_interacao = time.time()
                    proximo_intervalo_silencio = calcular_intervalo_silencio(configuracao)
                    solicitar_feedback_professor(fala_usuario)

                # ==========================================
                # 2. SILÊNCIO
                # ==========================================
                else:
                    tempo_decorrido = time.time() - ultimo_momento_interacao
                    if configuracao["silence_chat"] and tempo_decorrido > proximo_intervalo_silencio:
                        
                        # GATILHO VISUAL POR AR MORTO (40% de chance)
                        analise_agendada = False
                        if random.random() < 0.40:
                            analise_agendada = agendar_analise_visual(aguardar_resposta=True)

                        if not analise_agendada:
                            emitir_respostas(None, silencioso=True)
                            
                        ultimo_momento_interacao = time.time()
                        proximo_intervalo_silencio = calcular_intervalo_silencio(configuracao)
                        
    except Exception as e:
        import traceback
        erro_real = traceback.format_exc()
        emitir_log(f"ERRO CRÍTICO NO LOOP: {erro_real}")
        emitir_evento("error", mensagem=f"Erro fatal: {str(e)}")
    finally:
        executor_visual.shutdown(wait=False, cancel_futures=True)
        executor_professor.shutdown(wait=True, cancel_futures=False)


def _resposta_visual_valida(texto):
    texto = texto.strip()
    if not texto:
        return False

    if re.fullmatch(r"[\s\[\](){}<>,;:+\-./%\d]+", texto):
        return False

    palavras = re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", texto, flags=re.UNICODE)
    return len(palavras) >= 4


def _motivo_resposta_visual_invalida(texto):
    texto = texto.strip()
    if not texto:
        return "resposta vazia"
    if re.fullmatch(r"[\s\[\](){}<>,;:+\-./%\d]+", texto):
        return "resposta apenas numérica"
    if len(re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", texto, flags=re.UNICODE)) < 4:
        return "resposta curta ou incompleta"
    return "resposta sem texto descritivo"


def _limpar_resposta_visual(texto):
    frases = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", texto).strip())
    frases_unicas = []
    vistas = set()

    for frase in frases:
        chave = re.sub(r"[^\w\s]", "", frase.casefold()).strip()
        if not chave or chave in vistas:
            continue
        vistas.add(chave)
        frases_unicas.append(frase)
        if len(frases_unicas) == 4:
            break

    return " ".join(frases_unicas)


def _extrair_assunto_visual(fala):
    fala = re.sub(r"\s+", " ", fala).strip()
    fala = re.sub(r"^(?:(?:no|now|hey|chat)[,:]?\s+)+", "", fala, flags=re.IGNORECASE)
    fala = re.sub(
        r"^(?:look|see|watch)(?:\s+at)?\s+|^(?:olha|veja)(?:\s+(?:para|só))?\s+",
        "",
        fala,
        count=1,
        flags=re.IGNORECASE,
    )
    fala = re.sub(r"^(?:what(?:'s|\s+is)|who(?:'s|\s+is))\s+", "", fala, flags=re.IGNORECASE)
    fala = re.sub(r"^(?:this|that)\s+", "", fala, flags=re.IGNORECASE)
    assunto = fala.strip(" ,.!?")

    if assunto.casefold() in {"this", "that", "it", "this one", "that one"}:
        return ""
    if re.match(r"^(?:on|in|at|near|there)\b", assunto, flags=re.IGNORECASE):
        return ""
    return assunto


def capturar_e_analisar_tela(
    fala_do_streamer=None,
    tema_live=None,
    documento_worldbuilding=None,
    nome_jogo_worldbuilding=None,
):
    inicio_analise = time.perf_counter()
    inicio_requisicao = None
    try:
        emitir_log("Diretor de Visão: Iniciando captura da tela (Local)...")

        inicio_captura = time.perf_counter()
        with mss.MSS() as sct:
            monitor = sct.monitors[1]  
            sct_img = sct.grab(monitor)
        emitir_log(
            f"Diretor de Visão: captura do monitor {sct_img.width}x{sct_img.height} "
            f"em {time.perf_counter() - inicio_captura:.2f}s."
        )

        inicio_processamento = time.perf_counter()
        print_tela = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        print_tela.thumbnail((768, 768))
        emitir_log(
            f"Diretor de Visão: conversão/redimensionamento para "
            f"{print_tela.width}x{print_tela.height} em "
            f"{time.perf_counter() - inicio_processamento:.2f}s."
        )

        inicio_compactacao = time.perf_counter()
        buffer = io.BytesIO()
        print_tela.save(buffer, format="JPEG", quality=95)
        imagem_bytes = buffer.getvalue()
        imagem_base64 = base64.b64encode(imagem_bytes).decode('utf-8')
        emitir_log(
            f"Diretor de Visão: JPEG/base64 preparado em "
            f"{time.perf_counter() - inicio_compactacao:.2f}s "
            f"({len(imagem_bytes) / 1024:.1f} KiB JPEG; "
            f"{len(imagem_base64) / 1024:.1f} KiB base64)."
        )

        contexto_worldbuilding = selecionar_contexto_worldbuilding(documento_worldbuilding)
        
        # 1. Prompt draconiano para forçar o foco no seu jogo
        prompt_visao = f"""You are a strict, objective visual analyzer dedicated EXCLUSIVELY to the game '{nome_jogo_worldbuilding or 'Unspecified'}'.
        
        [GAME KNOWLEDGE BASE]
        Live Theme: {tema_live.strip() if tema_live else 'Unspecified'}
        Context: {contexto_worldbuilding if contexto_worldbuilding else 'None'}

        TASK: Describe what is CURRENTLY happening in this screenshot in 1 to 3 concise sentences.
        
        CRITICAL RULES:
        1. FORBIDDEN FRANCHISES: NEVER mention "The Witcher", "Geralt", "Skyrim", or any other game franchise. This image is 100% from '{nome_jogo_worldbuilding or 'Unspecified'}'.
        2. NO LORE HALLUCINATION: Focus STRICTLY on the immediate action, visible UI/HUD, and visible entities. Do not invent background stories.
        3. STRICT NAMING: Use the [GAME KNOWLEDGE BASE] for names. If a creature or item does not perfectly match the text, explicitly call it an "unidentified creature" or "unknown object". Do NOT guess names.
        4. LANGUAGE MANDATORY: You MUST write your entire description EXCLUSIVELY IN ENGLISH. Do not use Portuguese or any other language, even if the [GAME KNOWLEDGE BASE] contains it.
        Return ONLY the raw visual description."""

        if fala_do_streamer and fala_do_streamer.strip():
            assunto_visual = _extrair_assunto_visual(fala_do_streamer)
            if assunto_visual:
                prompt_visao += f"\n\nUSER QUESTION: The streamer specifically asked about '{assunto_visual}'. Address this if it is visible."

        # 2. Temperatura reduzida a ZERO para cortar invenções
        payload = {
            "model": MODELO_VISAO,
            "prompt": prompt_visao,
            "images": [imagem_base64],
            "stream": False,
            "options": {
                "temperature": 0.0, # Zera a criatividade do modelo visual
                "repeat_penalty": 1.15
            }
        }

        emitir_log(f"Diretor de Visão: enviando imagem ao Ollama ({MODELO_VISAO}).")
        inicio_requisicao = time.perf_counter()
        resposta = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        resposta.raise_for_status()
        emitir_log(
            f"Diretor de Visão: Ollama respondeu em "
            f"{time.perf_counter() - inicio_requisicao:.2f}s."
        )

        inicio_leitura = time.perf_counter()
        dados_ollama = resposta.json()
        resposta_bruta = str(dados_ollama.get("response", "")).strip()
        texto_resposta = _limpar_resposta_visual(resposta_bruta)
        emitir_log(
            f"Diretor de Visão: leitura e validação da resposta em "
            f"{time.perf_counter() - inicio_leitura:.2f}s."
        )

        if _resposta_visual_valida(texto_resposta):
            descricao = texto_resposta
        else:
            emitir_log(f"Diretor de Visão: Resposta inválida. Retorno bruto: {resposta_bruta[:240]!r}")
            return None
        
        emitir_log(
            f"Diretor de Visão finalizou em {time.perf_counter() - inicio_analise:.2f}s. "
            f"Descrição: {descricao}"
        )
        return descricao
        
    except requests.exceptions.RequestException as e:
        if inicio_requisicao is not None:
            emitir_log(
                f"Diretor de Visão: requisição falhou após "
                f"{time.perf_counter() - inicio_requisicao:.2f}s."
            )
        emitir_log(f"Erro de conexão com o Ollama local: {e}")
        return None
    except Exception as e:
        emitir_log(f"Diretor de Visão: falha após {time.perf_counter() - inicio_analise:.2f}s.")
        emitir_log(f"Erro na análise visual local: {e}")
        return None
if __name__ == "__main__":
    iniciar_live()
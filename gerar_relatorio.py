import json
import os
import sys
from dotenv import load_dotenv


PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
CAMINHO_HISTORICO = os.path.join(PASTA_PROJETO, "historico_live.txt")
CAMINHO_HISTORICO_PROFESSOR = os.path.join(PASTA_PROJETO, "historico_professor.json")
CAMINHO_HISTORICO_PROFESSOR_LEGADO = os.path.join(PASTA_PROJETO, "historico_professor.jsonl")
CAMINHO_JSON = os.path.join(PASTA_PROJETO, "relatorio_final.json")
CAMINHO_MARKDOWN = os.path.join(PASTA_PROJETO, "relatorio_final.md")
load_dotenv(os.path.join(PASTA_PROJETO, ".env"), override=False)

SCHEMA_RELATORIO = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}, "why_it_matters": {"type": "string"}},
            "required": ["pattern", "evidence", "why_it_matters"], "additionalProperties": False,
        }},
        "weaknesses": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}},
                "frequency": {"type": "integer"}, "impact": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "classification": {"type": "string", "enum": ["grammar", "word_choice", "sentence_structure", "possible_transcription_issue"]},
            },
            "required": ["pattern", "evidence", "frequency", "impact", "confidence", "classification"], "additionalProperties": False,
        }},
        "improvements": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "focus": {"type": "string"}, "why": {"type": "string"}, "exercise": {"type": "string"},
                "example": {"type": "string"}, "goal": {"type": "string"}, "priority": {"type": "integer"},
            },
            "required": ["focus", "why", "exercise", "example", "goal", "priority"], "additionalProperties": False,
        }},
        "corrections": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "original": {"type": "string"}, "corrected": {"type": "string"}, "explanation": {"type": "string"},
                "category": {"type": "string", "enum": ["grammar", "word_choice", "structure", "naturalness"]},
                "importance": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["original", "corrected", "explanation", "category", "importance"], "additionalProperties": False,
        }},
        "vocabulary": {"type": "array", "items": {
            "type": "object",
            "properties": {"original": {"type": "string"}, "suggestion": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["original", "suggestion", "reason"], "additionalProperties": False,
        }},
        "transcription_notes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "transcript_text": {"type": "string"}, "possible_phrase": {"type": "string"},
                "reason": {"type": "string"}, "next_step": {"type": "string"},
            },
            "required": ["transcript_text", "possible_phrase", "reason", "next_step"], "additionalProperties": False,
        }},
        "metrics": {"type": "object", "properties": {
            chave: {"type": "object", "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "evidence": {"type": "string"},
            }, "required": ["score", "confidence", "evidence"], "additionalProperties": False}
            for chave in ("fluency", "grammar", "vocabulary", "clarity")
        }, "required": ["fluency", "grammar", "vocabulary", "clarity"], "additionalProperties": False},
    },
    "required": ["summary", "strengths", "weaknesses", "improvements", "corrections", "vocabulary", "transcription_notes", "metrics"],
    "additionalProperties": False,
}


def ler_historico():
    if not os.path.exists(CAMINHO_HISTORICO):
        return ""

    with open(CAMINHO_HISTORICO, "r", encoding="utf-8") as arquivo:
        falas_streamer = [
            linha.removeprefix("Streamer:").strip()
            for linha in arquivo
            if linha.startswith("Streamer:")
        ]
    return "\n".join(falas_streamer)[-50000:]


def ler_historico_professor():
    registros = None
    if os.path.exists(CAMINHO_HISTORICO_PROFESSOR):
        with open(CAMINHO_HISTORICO_PROFESSOR, "r", encoding="utf-8") as arquivo:
            try:
                sessoes = json.load(arquivo)
            except json.JSONDecodeError:
                sessoes = []
        if isinstance(sessoes, list) and sessoes:
            ultima_sessao = sessoes[-1]
            registros = ultima_sessao.get("interactions", []) if isinstance(ultima_sessao, dict) else []

    if registros is None and os.path.exists(CAMINHO_HISTORICO_PROFESSOR_LEGADO):
        registros = []
        with open(CAMINHO_HISTORICO_PROFESSOR_LEGADO, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                try:
                    registro = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if isinstance(registro, dict):
                    registros.append(registro)

    if not isinstance(registros, list):
        return ""

    interacoes = []
    for registro in registros:
        if not isinstance(registro, dict):
            continue
        original = str(registro.get("original", "")).strip()
        correcao = str(registro.get("correcao", "")).strip()
        explicacao = str(registro.get("explicacao", "")).strip()
        if original and correcao and explicacao:
            interacoes.append(
                f"Fala: {original}\nCorreção: {correcao}\nExplicação: {explicacao}"
            )
    return "\n\n".join(interacoes)[-30000:]


def relatorio_sem_falas(mensagem):
    return {
        "summary": mensagem,
        "strengths": [],
        "weaknesses": [],
        "improvements": [],
        "corrections": [],
        "vocabulary": [],
        "transcription_notes": [],
        "metrics": {
            chave: {"score": 0, "confidence": "low", "evidence": "Sem falas suficientes."}
            for chave in ("fluency", "grammar", "vocabulary", "clarity")
        },
        "hasTranscript": False,
    }


def normalizar_relatorio(dados):
    if not isinstance(dados, dict):
        raise ValueError("O relatório retornado não é um objeto JSON.")

    def texto(valor, limite=3000):
        if not isinstance(valor, str):
            return ""
        return valor.strip()[:limite]

    def lista_estruturada(chave, campos, limite=20):
        valor = dados.get(chave, [])
        if not isinstance(valor, list):
            return []
        resultado = []
        for item in valor[:limite]:
            if isinstance(item, str):
                item = {campos[0]: item}
            if not isinstance(item, dict):
                continue
            normalizado = {}
            for campo in campos:
                campo_valor = item.get(campo, "")
                if campo in {"frequency", "priority"}:
                    try:
                        normalizado[campo] = max(0, int(campo_valor))
                    except (TypeError, ValueError):
                        normalizado[campo] = 0
                elif campo == "evidence" and isinstance(campo_valor, list):
                    normalizado[campo] = [texto(exemplo, 500) for exemplo in campo_valor if texto(exemplo, 500)][:8]
                else:
                    normalizado[campo] = texto(campo_valor)
            if any(valor for valor in normalizado.values()):
                resultado.append(normalizado)
        return resultado

    metricas_recebidas = dados.get("metrics", {})
    if not isinstance(metricas_recebidas, dict):
        metricas_recebidas = {}

    metricas = {}
    for chave in ("fluency", "grammar", "vocabulary", "clarity"):
        valor = metricas_recebidas.get(chave, {})
        if not isinstance(valor, dict):
            valor = {"score": valor}
        try:
            score = max(0, min(100, int(valor.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        confianca = valor.get("confidence", "low")
        if not isinstance(confianca, str) or confianca not in {"low", "medium", "high"}:
            confianca = "low"
        metricas[chave] = {
            "score": score,
            "confidence": confianca,
            "evidence": texto(valor.get("evidence", "")),
        }

    return {
        "summary": texto(dados.get("summary", "Sessão concluída."), 5000),
        "strengths": lista_estruturada("strengths", ("pattern", "evidence", "why_it_matters")),
        "weaknesses": lista_estruturada("weaknesses", ("pattern", "evidence", "frequency", "impact", "confidence", "classification")),
        "improvements": lista_estruturada("improvements", ("focus", "why", "exercise", "example", "goal", "priority")),
        "corrections": lista_estruturada("corrections", ("original", "corrected", "explanation", "category", "importance"), 30),
        "vocabulary": lista_estruturada("vocabulary", ("original", "suggestion", "reason"), 20),
        "transcription_notes": lista_estruturada(
            "transcription_notes",
            ("transcript_text", "possible_phrase", "reason", "next_step"),
            12,
        ),
        "metrics": metricas,
        "hasTranscript": True,
    }


def gerar_relatorio(falas, historico_professor=""):
    chave_api = os.environ.get("OPENAI_API_KEY")
    if not chave_api:
        return {
            **relatorio_sem_falas("A análise personalizada não foi gerada."),
            "hasTranscript": True,
            "error": "OPENAI_API_KEY não está configurada. Preencha o arquivo .env na raiz do projeto.",
        }

    from openai import OpenAI

    system_prompt = """
You are an English speaking coach reviewing a gaming livestream transcript.
Return a detailed but readable JSON report in Portuguese with this exact shape:
{
    "summary": "two or three substantive paragraphs covering the session and the learner's overall trajectory",
    "strengths": [{"pattern":"specific demonstrated skill","evidence":["exact transcript evidence"],"why_it_matters":"why this skill helps communication"}],
    "weaknesses": [{"pattern":"recurring language pattern, not an isolated phrase","evidence":["exact examples"],"frequency":0,"impact":"how it affects clarity or naturalness","confidence":"low|medium|high","classification":"grammar|word_choice|sentence_structure|possible_transcription_issue"}],
    "improvements": [{"focus":"one priority","why":"connection to observed evidence","exercise":"a short repeatable drill","example":"model sentence","goal":"what improvement should sound like","priority":1}],
    "corrections": [{"original":"exact transcript quote","corrected":"natural correction","explanation":"clear Portuguese explanation of the rule","category":"grammar|word_choice|structure|naturalness","importance":"high|medium|low"}],
    "vocabulary": [{"original":"phrase used or context","suggestion":"natural gaming expression","reason":"when and why it fits"}],
    "transcription_notes": [{"transcript_text":"possibly mistranscribed text","possible_phrase":"plausible intended phrase","reason":"contextual evidence and uncertainty","next_step":"how to verify without calling it a pronunciation error"}],
    "metrics": {"fluency":{"score":0,"confidence":"low|medium|high","evidence":"textual evidence"},"grammar":{"score":0,"confidence":"low|medium|high","evidence":"textual evidence"},"vocabulary":{"score":0,"confidence":"low|medium|high","evidence":"textual evidence"},"clarity":{"score":0,"confidence":"low|medium|high","evidence":"textual evidence"}}
}
Give a useful explanation, not just a summary. Identify repeated patterns across the session and distinguish recurring issues from one-off slips. Provide up to 8 specific strengths, 10 recurring attention patterns, 8 practical exercises, 20 meaningful corrections, 12 vocabulary suggestions, and 10 possible transcription notes; use fewer when evidence is insufficient.
Only quote speech that appears verbatim in the transcript. Do not invent mistakes, achievements, or details. Treat real-time teacher feedback as supporting evidence, not unquestionable truth.
The transcript comes from speech recognition. If a phrase resembles a game title, proper noun, or contextually likely expression but appears mistranscribed (for example, "Path of isaia" could be "Path of Exile"), put it in transcription_notes. Never label that as a grammar, vocabulary, or pronunciation failure unless the audio was actually analyzed. Text alone cannot prove a phoneme such as L was mispronounced.
Repeated greetings, fillers, informal contractions, and harmless repetition are not errors. Do not criticize them. Analyze fluency and clarity from sentence flow and organization only; pronunciation is not measured here.
Metrics are instructional estimates from this session's text, not formal proficiency scores or pronunciation measurements. Use integer scores from 0 to 100, a confidence level, and concrete text evidence for every metric. When evidence is weak, use low confidence instead of pretending precision.
Keep feedback supportive, specific, and actionable. Do not pad the report with generic praise or repeat the same advice in multiple sections.
"""

    client = OpenAI(api_key=chave_api, timeout=90.0, max_retries=1)
    resposta = client.responses.create(
        input=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Transcript:\n{falas}\n\n"
                    f"Real-time teacher feedback:\n{historico_professor or 'No teacher feedback available.'}"
                ),
            },
        ],
        model="gpt-6.1-sol",
        max_output_tokens=5000,
        reasoning={"effort": "medium"},
        text={
            "format": {
                "type": "json_schema",
                "name": "english_session_report",
                "strict": True,
                "schema": SCHEMA_RELATORIO,
            }
        },
    )
    if resposta.status != "completed":
        raise RuntimeError(f"A OpenAI não concluiu o relatório (status: {resposta.status}).")
    conteudo = resposta.output_text
    return normalizar_relatorio(json.loads(conteudo))


def gerar_markdown(relatorio):
    secoes = [f"# Relatório da live\n\n{relatorio['summary']}"]

    metricas = ["## Indicadores da sessão"]
    for chave, metrica in relatorio["metrics"].items():
        metricas.append(
            f"- **{chave.title()}**: {metrica['score']}/100 "
            f"(confiança {metrica['confidence']}). {metrica['evidence']}"
        )
    secoes.append("\n".join(metricas))

    for chave, titulo, campos in (
        ("strengths", "Pontos fortes", (("evidence", "Evidências"), ("why_it_matters", "Por que importa"))),
        ("weaknesses", "Padrões a desenvolver", (("evidence", "Exemplos"), ("frequency", "Ocorrências"), ("impact", "Impacto"), ("confidence", "Confiança"))),
        ("improvements", "Plano de prática", (("why", "Por que praticar"), ("exercise", "Exercício"), ("example", "Exemplo"), ("goal", "Meta"))),
    ):
        itens = []
        for item in relatorio[chave]:
            if isinstance(item, str):
                itens.append(f"- {item}")
                continue
            titulo_item = item.get("pattern") or item.get("focus") or "Observação"
            linhas = [f"- **{titulo_item}**"]
            for campo, rotulo in campos:
                valor = item.get(campo)
                if isinstance(valor, list):
                    valor = "; ".join(valor)
                if valor:
                    linhas.append(f"  - {rotulo}: {valor}")
            itens.append("\n".join(linhas))
        secoes.append(f"## {titulo}\n" + ("\n".join(itens) or "Sem itens nesta sessão."))

    secoes.append("## Correções importantes\n" + "\n".join(
        f"- **{item['original']}** → **{item['corrected']}** ({item.get('category', 'geral')}, {item.get('importance', 'relevância não informada')}): {item['explanation']}"
        for item in relatorio["corrections"]
    ))
    secoes.append("## Vocabulário\n" + "\n".join(
        f"- **{item['original']}** → **{item['suggestion']}**: {item['reason']}"
        for item in relatorio["vocabulary"]
    ))
    if relatorio["transcription_notes"]:
        secoes.append("## Possíveis falhas de transcrição\n" + "\n".join(
            f"- **{item['transcript_text']}**; possível frase: **{item['possible_phrase']}**. "
            f"{item['reason']} Próximo passo: {item['next_step']}"
            for item in relatorio["transcription_notes"]
        ))
    return "\n\n".join(secoes).strip() + "\n"


def main():
    falas = ler_historico()
    historico_professor = ler_historico_professor()
    if not falas.strip():
        relatorio = relatorio_sem_falas("Esta sessão não teve falas transcritas para avaliar.")
    else:
        try:
            relatorio = gerar_relatorio(falas, historico_professor)
        except Exception as erro:
            print(f"[report-error] {erro}", file=sys.stderr, flush=True)
            relatorio = {
                **relatorio_sem_falas("Não foi possível gerar a análise personalizada."),
                "hasTranscript": True,
                "error": "A análise da IA falhou. O histórico e o resumo local continuam disponíveis.",
            }

    with open(CAMINHO_JSON, "w", encoding="utf-8") as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)
    with open(CAMINHO_MARKDOWN, "w", encoding="utf-8") as arquivo:
        arquivo.write(gerar_markdown(relatorio))

    sys.stdout.write(json.dumps(relatorio, ensure_ascii=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
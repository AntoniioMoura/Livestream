import json
import os
import sys


PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
CAMINHO_HISTORICO = os.path.join(PASTA_PROJETO, "historico_live.txt")
CAMINHO_JSON = os.path.join(PASTA_PROJETO, "relatorio_final.json")
CAMINHO_MARKDOWN = os.path.join(PASTA_PROJETO, "relatorio_final.md")


def ler_historico():
    if not os.path.exists(CAMINHO_HISTORICO):
        return ""

    with open(CAMINHO_HISTORICO, "r", encoding="utf-8") as arquivo:
        falas_streamer = [
            linha.removeprefix("Streamer:").strip()
            for linha in arquivo
            if linha.startswith("Streamer:")
        ]
    return "\n".join(falas_streamer)[-12000:]


def relatorio_sem_falas(mensagem):
    return {
        "summary": mensagem,
        "strengths": ["Você concluiu a sessão de prática e pode tentar novamente na próxima live."],
        "weaknesses": ["Não houve frases transcritas suficientes para avaliar o inglês."],
        "improvements": ["Use frases curtas em inglês e faça uma pausa para o reconhecimento de voz concluir cada trecho."],
        "corrections": [],
        "vocabulary": [],
        "metrics": {"fluency": 0, "grammar": 0, "vocabulary": 0, "clarity": 0},
        "hasTranscript": False,
    }


def normalizar_relatorio(dados):
    if not isinstance(dados, dict):
        raise ValueError("O relatório retornado não é um objeto JSON.")

    def lista_textos(chave, limite=4):
        valor = dados.get(chave, [])
        if not isinstance(valor, list):
            return []
        return [item.strip()[:500] for item in valor if isinstance(item, str) and item.strip()][:limite]

    def lista_pares(chave, campos, limite=4):
        valor = dados.get(chave, [])
        if not isinstance(valor, list):
            return []
        resultado = []
        for item in valor[:limite]:
            if not isinstance(item, dict):
                continue
            resultado.append({
                campo: str(item.get(campo, "")).strip()[:500]
                for campo in campos
            })
        return resultado

    metricas_recebidas = dados.get("metrics", {})
    if not isinstance(metricas_recebidas, dict):
        metricas_recebidas = {}

    metricas = {}
    for chave in ("fluency", "grammar", "vocabulary", "clarity"):
        try:
            metricas[chave] = max(0, min(100, int(metricas_recebidas.get(chave, 0))))
        except (TypeError, ValueError):
            metricas[chave] = 0

    return {
        "summary": str(dados.get("summary", "Sessão concluída."))[:1000],
        "strengths": lista_textos("strengths"),
        "weaknesses": lista_textos("weaknesses"),
        "improvements": lista_textos("improvements"),
        "corrections": lista_pares("corrections", ("original", "corrected", "explanation")),
        "vocabulary": lista_pares("vocabulary", ("original", "suggestion", "reason")),
        "metrics": metricas,
        "hasTranscript": True,
    }


def gerar_relatorio(falas):
    chave_api = os.environ.get("GROQ_API_KEY")
    if not chave_api:
        return {
            **relatorio_sem_falas("A análise personalizada não foi gerada."),
            "hasTranscript": True,
            "error": "GROQ_API_KEY não está configurada no ambiente do aplicativo.",
        }

    from groq import Groq

    system_prompt = """
You are an English speaking coach reviewing a gaming livestream transcript.
Return ONLY valid JSON in Portuguese with this exact shape:
{
  "summary": "short supportive assessment",
  "strengths": ["up to 3 concrete strengths"],
  "weaknesses": ["up to 3 observable difficulties"],
  "improvements": ["up to 3 actionable practice suggestions"],
  "corrections": [{"original":"exact quote from transcript","corrected":"natural correction","explanation":"brief Portuguese explanation"}],
  "vocabulary": [{"original":"phrase used or context","suggestion":"natural gaming expression","reason":"why it fits"}],
  "metrics": {"fluency": 0, "grammar": 0, "vocabulary": 0, "clarity": 0}
}
Metrics are subjective learning estimates from text only, not pronunciation measurements. Use integer scores from 0 to 100.
Only quote speech that appears verbatim in the transcript. Do not invent mistakes, achievements, or details.
If evidence is insufficient, say so and leave corrections or vocabulary empty. Keep the response concise and supportive.
"""

    client = Groq(api_key=chave_api, timeout=40.0, max_retries=0)
    resposta = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transcript:\n{falas}"},
        ],
        model="qwen/qwen3.8-27b",
        temperature=0.35,
        max_tokens=1400,
    )
    conteudo = resposta.choices[0].message.content.strip()
    conteudo = conteudo.removeprefix("```json").removesuffix("```").strip()
    return normalizar_relatorio(json.loads(conteudo))


def gerar_markdown(relatorio):
    secoes = [f"# Relatório da live\n\n{relatorio['summary']}"]
    for chave, titulo in (("strengths", "Pontos fortes"), ("weaknesses", "Pontos de atenção"), ("improvements", "Próximos passos")):
        linhas = "\n".join(f"- {item}" for item in relatorio[chave]) or "- Sem itens nesta sessão."
        secoes.append(f"## {titulo}\n{linhas}")
    secoes.append("## Correções\n" + "\n".join(
        f"- **{item['original']}** → **{item['corrected']}**: {item['explanation']}"
        for item in relatorio["corrections"]
    ))
    secoes.append("## Vocabulário\n" + "\n".join(
        f"- **{item['original']}** → **{item['suggestion']}**: {item['reason']}"
        for item in relatorio["vocabulary"]
    ))
    return "\n\n".join(secoes).strip() + "\n"


def main():
    falas = ler_historico()
    if not falas.strip():
        relatorio = relatorio_sem_falas("Esta sessão não teve falas transcritas para avaliar.")
    else:
        try:
            relatorio = gerar_relatorio(falas)
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
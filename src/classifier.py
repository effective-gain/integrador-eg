import json
import logging
from pathlib import Path
from datetime import datetime

import anthropic

from .models import (
    AcaoTipo,
    ClassificacaoResult,
    MensagemEntrada,
    Prioridade,
    GRUPOS_PROJETOS,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classifier.md"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024


def _projeto_do_grupo(grupo_nome: str) -> str:
    nome_lower = grupo_nome.lower()
    for chave, projeto in GRUPOS_PROJETOS.items():
        if chave in nome_lower:
            return projeto
    return grupo_nome  # fallback: usa o próprio nome do grupo


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _montar_prompt(mensagem: MensagemEntrada, projeto: str) -> str:
    template = _carregar_prompt()
    # usar replace manual evita conflito com chaves {} do JSON no template
    return (
        template
        .replace("{grupo_nome}", mensagem.grupo_nome)
        .replace("{projeto}", projeto)
        .replace("{timestamp}", mensagem.timestamp.strftime("%Y-%m-%d %H:%M"))
        .replace("{remetente}", mensagem.remetente)
        .replace("{conteudo}", mensagem.conteudo)
    )


def _parse_resultado(raw: str, projeto: str) -> ClassificacaoResult:
    try:
        data = json.loads(raw.strip())
        return ClassificacaoResult(
            acao=AcaoTipo(data["acao"]),
            projeto=data.get("projeto", projeto),
            conteudo_formatado=data["conteudo_formatado"],
            prioridade=Prioridade(data.get("prioridade", "media")),
            requer_esclarecimento=data.get("requer_esclarecimento", False),
            pergunta_esclarecimento=data.get("pergunta_esclarecimento"),
            resumo_confirmacao=data["resumo_confirmacao"],
            idioma_detectado=data.get("idioma_detectado", "pt"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Falha no parse do classificador: %s | raw: %s", e, raw[:200])
        # fallback seguro: marca como ambígua para não agir no escuro
        return ClassificacaoResult(
            acao=AcaoTipo.AMBIGUA,
            projeto=projeto,
            conteudo_formatado=raw,
            requer_esclarecimento=True,
            pergunta_esclarecimento="Não entendi bem o que você precisa. Pode detalhar?",
            resumo_confirmacao="Não entendi bem o que você precisa. Pode detalhar?",
        )


class Classifier:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def classificar(self, mensagem: MensagemEntrada) -> ClassificacaoResult:
        projeto = _projeto_do_grupo(mensagem.grupo_nome)
        prompt = _montar_prompt(mensagem, projeto)

        logger.info("Classificando mensagem do grupo '%s' → projeto '%s'", mensagem.grupo_nome, projeto)

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
            resultado = _parse_resultado(raw, projeto)

            logger.info(
                "Classificação: acao=%s requer_esclarecimento=%s idioma=%s",
                resultado.acao,
                resultado.requer_esclarecimento,
                resultado.idioma_detectado,
            )
            return resultado

        except anthropic.APIError as e:
            logger.error("Erro na API Anthropic: %s", e)
            raise

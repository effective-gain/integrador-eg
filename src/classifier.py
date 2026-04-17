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

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classifier_system.md"
USER_PROMPT_PATH   = Path(__file__).parent.parent / "prompts" / "classifier_user.md"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 512


def _projeto_do_grupo(grupo_nome: str) -> str:
    nome_lower = grupo_nome.lower()
    for chave, projeto in GRUPOS_PROJETOS.items():
        if chave in nome_lower:
            return projeto
    return grupo_nome


def _montar_user_message(mensagem: MensagemEntrada, projeto: str) -> str:
    template = USER_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{grupo_nome}", mensagem.grupo_nome)
        .replace("{projeto}", projeto)
        .replace("{timestamp}", mensagem.timestamp.strftime("%Y-%m-%d %H:%M"))
        .replace("{remetente}", mensagem.remetente)
        .replace("{conteudo}", mensagem.conteudo)
    )


def _montar_system_blocks(dna_projeto: str) -> list[dict]:
    """
    Monta os blocos de system com cache_control seguindo o padrão EG OS:
      Bloco 1 — Instruções estáticas do classificador (CACHED)
      Bloco 2 — DNA narrativo do projeto (CACHED quando presente)
    """
    instrucoes = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    blocos: list[dict] = [
        {
            "type": "text",
            "text": instrucoes,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    if dna_projeto.strip():
        blocos.append({
            "type": "text",
            "text": f"## DNA DO PROJETO\n\n{dna_projeto}",
            "cache_control": {"type": "ephemeral"},
        })

    return blocos


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

    def classificar(self, mensagem: MensagemEntrada, dna_projeto: str = "") -> ClassificacaoResult:
        projeto = _projeto_do_grupo(mensagem.grupo_nome)
        system_blocks = _montar_system_blocks(dna_projeto)
        user_message = _montar_user_message(mensagem, projeto)

        com_dna = bool(dna_projeto.strip())
        logger.info(
            "Classificando | grupo='%s' projeto='%s' dna=%s",
            mensagem.grupo_nome, projeto, "sim" if com_dna else "não",
        )

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_blocks,
                messages=[{"role": "user", "content": user_message}],
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

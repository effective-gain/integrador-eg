"""
Classifica e-mails com Claude e gera digest para WhatsApp.
"""
import json
import logging
from datetime import datetime

import anthropic

from .models import EmailCategoria, EmailClassificado, EmailEntrada
from .email_reader import extrair_codigo_2fa

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"  # haiku: mais rápido e barato para classificação em lote
MAX_TOKENS = 512

_PROMPT_CLASSIFICAR = """Você é um assistente que classifica e-mails de negócios.

E-mail recebido:
De: {remetente}
Assunto: {assunto}
Corpo: {corpo}

Classifique e responda APENAS com JSON válido:
{{
  "categoria": "invoice|task|codigo_2fa|informativo|spam",
  "resumo": "resumo em 1 frase, max 100 chars",
  "urgente": true|false,
  "acao_sugerida": "o que fazer com este e-mail (null se não há ação)"
}}

Regras:
- codigo_2fa: contém código de verificação/autenticação
- invoice: fatura, recibo, nota fiscal, payment
- task: pede ação específica (responder, assinar, aprovar)
- informativo: newsletter, notificação sem ação necessária
- spam: promoção, marketing não solicitado
- urgente: true apenas se tem prazo ou impacto financeiro imediato"""


def _classificar_com_claude(client: anthropic.Anthropic, entrada: EmailEntrada) -> EmailClassificado:
    corpo_truncado = entrada.corpo[:800] if len(entrada.corpo) > 800 else entrada.corpo
    prompt = (
        _PROMPT_CLASSIFICAR
        .replace("{remetente}", entrada.remetente)
        .replace("{assunto}", entrada.assunto)
        .replace("{corpo}", corpo_truncado)
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        data = json.loads(raw)

        codigo_2fa = None
        if data.get("categoria") == "codigo_2fa":
            codigo_2fa = extrair_codigo_2fa(entrada.corpo) or extrair_codigo_2fa(entrada.assunto)

        return EmailClassificado(
            email=entrada,
            categoria=EmailCategoria(data["categoria"]),
            resumo=data["resumo"],
            urgente=data.get("urgente", False),
            codigo_2fa=codigo_2fa,
            acao_sugerida=data.get("acao_sugerida"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Falha ao classificar email '%s': %s", entrada.assunto, e)
        return EmailClassificado(
            email=entrada,
            categoria=EmailCategoria.INFORMATIVO,
            resumo=entrada.assunto[:100],
            urgente=False,
        )


def classificar_emails(
    client: anthropic.Anthropic,
    emails: list[EmailEntrada],
) -> list[EmailClassificado]:
    """Classifica lista de e-mails. Pula spam automaticamente."""
    resultado = []
    for em in emails:
        classificado = _classificar_com_claude(client, em)
        if classificado.categoria != EmailCategoria.SPAM:
            resultado.append(classificado)
            logger.info(
                "Email '%s' → %s (urgente=%s)",
                em.assunto[:50], classificado.categoria.value, classificado.urgente,
            )
    return resultado


def formatar_digest_whatsapp(emails_classificados: list[EmailClassificado], data: datetime | None = None) -> str:
    """
    Gera texto de digest formatado para WhatsApp.
    Máximo ~4000 chars (limite prático do WA).
    """
    if not emails_classificados:
        return "📧 Nenhum e-mail relevante hoje."

    data = data or datetime.now()
    linhas = [f"📧 *E-mail Digest — {data.strftime('%d/%m %H:%M')}*\n"]

    urgentes = [e for e in emails_classificados if e.urgente]
    outros = [e for e in emails_classificados if not e.urgente]

    if urgentes:
        linhas.append("🔴 *URGENTES*")
        for em in urgentes:
            emoji = _emoji_categoria(em.categoria)
            linhas.append(f"{emoji} {em.resumo}")
            if em.acao_sugerida:
                linhas.append(f"   → {em.acao_sugerida}")
            if em.codigo_2fa:
                linhas.append(f"   🔑 Código: *{em.codigo_2fa}*")
        linhas.append("")

    if outros:
        linhas.append("📋 *Outros*")
        for em in outros:
            emoji = _emoji_categoria(em.categoria)
            linhas.append(f"{emoji} {em.resumo}")

    linhas.append(f"\n_Total: {len(emails_classificados)} e-mails relevantes_")
    return "\n".join(linhas)


def _emoji_categoria(cat: EmailCategoria) -> str:
    return {
        EmailCategoria.INVOICE: "💰",
        EmailCategoria.TASK: "✅",
        EmailCategoria.CODIGO_2FA: "🔑",
        EmailCategoria.INFORMATIVO: "ℹ️",
        EmailCategoria.SPAM: "🗑️",
    }.get(cat, "📧")

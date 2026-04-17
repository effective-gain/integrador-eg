"""Testa classificação de e-mails e formatação do digest."""
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.email_digest import classificar_emails, formatar_digest_whatsapp, _emoji_categoria
from src.models import EmailCategoria, EmailClassificado, EmailEntrada


def _fazer_email(assunto="Assunto", corpo="Corpo", remetente="from@test.com") -> EmailEntrada:
    return EmailEntrada(
        uid="1",
        remetente=remetente,
        assunto=assunto,
        corpo=corpo,
        data=datetime(2026, 4, 17, 10, 0),
    )


def _mock_claude_resposta(categoria: str, resumo: str, urgente=False, acao=None):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "categoria": categoria,
        "resumo": resumo,
        "urgente": urgente,
        "acao_sugerida": acao,
    }))]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


# ── Classificação ─────────────────────────────────────────────────────────────

def test_classificar_invoice():
    client = _mock_claude_resposta("invoice", "Fatura de $500 recebida", urgente=True, acao="Conferir valor")
    emails = [_fazer_email("Invoice #1234", "Total: $500")]
    resultado = classificar_emails(client, emails)

    assert len(resultado) == 1
    assert resultado[0].categoria == EmailCategoria.INVOICE
    assert resultado[0].urgente is True


def test_classificar_codigo_2fa_extrai_codigo():
    client = _mock_claude_resposta("codigo_2fa", "Código de verificação recebido")
    emails = [_fazer_email("Seu código é", "Use o código 847291 para entrar")]
    resultado = classificar_emails(client, emails)

    assert resultado[0].categoria == EmailCategoria.CODIGO_2FA
    assert resultado[0].codigo_2fa == "847291"


def test_classificar_spam_e_filtrado():
    client = _mock_claude_resposta("spam", "Promoção irrelevante")
    emails = [_fazer_email("50% OFF apenas hoje!!!", "Compre agora")]
    resultado = classificar_emails(client, emails)

    assert resultado == []  # spam é descartado


def test_classificar_falha_json_retorna_informativo():
    msg = MagicMock()
    msg.content = [MagicMock(text="resposta inválida não é json")]
    client = MagicMock()
    client.messages.create.return_value = msg

    emails = [_fazer_email("E-mail qualquer")]
    resultado = classificar_emails(client, emails)

    assert resultado[0].categoria == EmailCategoria.INFORMATIVO


def test_classificar_multiplos_emails():
    respostas = [
        json.dumps({"categoria": "invoice", "resumo": "Fatura", "urgente": True}),
        json.dumps({"categoria": "task", "resumo": "Aprovar proposta", "urgente": False, "acao_sugerida": "Responder até sexta"}),
        json.dumps({"categoria": "spam", "resumo": "Promoção", "urgente": False}),
    ]
    msgs = [MagicMock(content=[MagicMock(text=r)]) for r in respostas]
    client = MagicMock()
    client.messages.create.side_effect = msgs

    emails = [
        _fazer_email("Fatura dezembro"),
        _fazer_email("Proposta comercial"),
        _fazer_email("Black Friday"),
    ]
    resultado = classificar_emails(client, emails)

    assert len(resultado) == 2  # spam removido
    categorias = [r.categoria for r in resultado]
    assert EmailCategoria.INVOICE in categorias
    assert EmailCategoria.TASK in categorias


# ── Formatação do digest ──────────────────────────────────────────────────────

def _fazer_classificado(categoria: EmailCategoria, resumo: str, urgente=False, codigo=None, acao=None):
    return EmailClassificado(
        email=_fazer_email(),
        categoria=categoria,
        resumo=resumo,
        urgente=urgente,
        codigo_2fa=codigo,
        acao_sugerida=acao,
    )


def test_digest_vazio():
    assert "Nenhum" in formatar_digest_whatsapp([])


def test_digest_com_urgentes_primeiro():
    emails = [
        _fazer_classificado(EmailCategoria.INFORMATIVO, "Newsletter semanal"),
        _fazer_classificado(EmailCategoria.INVOICE, "Fatura $500 vence hoje", urgente=True),
    ]
    digest = formatar_digest_whatsapp(emails)

    idx_urgente = digest.index("URGENTES")
    idx_outros = digest.index("Outros")
    assert idx_urgente < idx_outros


def test_digest_exibe_codigo_2fa():
    emails = [
        _fazer_classificado(EmailCategoria.CODIGO_2FA, "Código recebido", urgente=True, codigo="847291"),
    ]
    digest = formatar_digest_whatsapp(emails)
    assert "847291" in digest


def test_digest_exibe_acao_sugerida():
    emails = [
        _fazer_classificado(EmailCategoria.TASK, "Assinar contrato", urgente=True, acao="Responder até sexta"),
    ]
    digest = formatar_digest_whatsapp(emails)
    assert "Responder até sexta" in digest


def test_digest_total_correto():
    emails = [
        _fazer_classificado(EmailCategoria.INFORMATIVO, "Info 1"),
        _fazer_classificado(EmailCategoria.INFORMATIVO, "Info 2"),
    ]
    digest = formatar_digest_whatsapp(emails)
    assert "2 e-mails" in digest


def test_emoji_por_categoria():
    assert _emoji_categoria(EmailCategoria.INVOICE) == "💰"
    assert _emoji_categoria(EmailCategoria.CODIGO_2FA) == "🔑"
    assert _emoji_categoria(EmailCategoria.TASK) == "✅"

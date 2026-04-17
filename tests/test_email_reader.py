"""Testa EmailReader e funções utilitárias de e-mail."""
import email
import imaplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from unittest.mock import MagicMock, patch

import pytest

from src.email_reader import EmailReader, extrair_codigo_2fa, _decodificar_header, _extrair_corpo


# ── Utilitários ──────────────────────────────────────────────────────────────

def _fazer_msg(assunto="Teste", corpo="Corpo do e-mail", remetente="sender@test.com", com_anexo=False):
    if com_anexo:
        msg = MIMEMultipart()
        msg.attach(MIMEText(corpo, "plain"))
        anexo = MIMEBase("application", "octet-stream")
        anexo.add_header("Content-Disposition", "attachment", filename="doc.pdf")
        msg.attach(anexo)
    else:
        msg = MIMEMultipart()
        msg.attach(MIMEText(corpo, "plain"))
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["Date"] = "Fri, 17 Apr 2026 10:00:00 +0000"
    return msg.as_bytes()


# ── Testes: extrair_codigo_2fa ────────────────────────────────────────────────

def test_extrair_codigo_2fa_6_digitos():
    assert extrair_codigo_2fa("Seu código de verificação é 847291") == "847291"


def test_extrair_codigo_2fa_4_digitos():
    assert extrair_codigo_2fa("Use o código 5823 para confirmar.") == "5823"


def test_extrair_codigo_2fa_ignora_anos():
    resultado = extrair_codigo_2fa("Em 2026 você receberá o código 9182")
    assert resultado == "9182"


def test_extrair_codigo_2fa_sem_codigo():
    assert extrair_codigo_2fa("Bem-vindo ao serviço. Acesse seu painel.") is None


def test_extrair_codigo_2fa_ignora_portas_comuns():
    resultado = extrair_codigo_2fa("Porta 8080 está aberta. Código: 7743")
    assert resultado == "7743"


# ── Testes: _decodificar_header ───────────────────────────────────────────────

def test_decodificar_header_ascii():
    assert _decodificar_header("Assunto simples") == "Assunto simples"


def test_decodificar_header_none():
    assert _decodificar_header(None) == ""


# ── Testes: EmailReader (com IMAP mockado) ────────────────────────────────────

def _mock_imap(uids: list[bytes], mensagem_bytes: bytes):
    """Cria um mock completo do IMAP4_SSL."""
    conn = MagicMock()
    conn.select.return_value = ("OK", [None])
    conn.search.return_value = ("OK", [b" ".join(uids)])
    conn.fetch.return_value = ("OK", [(None, mensagem_bytes)])
    conn.logout.return_value = None
    return conn


def test_ler_nao_lidos_retorna_emails():
    msg_bytes = _fazer_msg(assunto="Invoice dezembro", corpo="Segue a fatura de $500")
    conn_mock = _mock_imap([b"1"], msg_bytes)

    with patch("src.email_reader.imaplib.IMAP4_SSL", return_value=conn_mock):
        reader = EmailReader("imap.gmail.com", "user@test.com", "senha")
        emails = reader.ler_nao_lidos(limite=10)

    assert len(emails) == 1
    assert "Invoice" in emails[0].assunto
    assert "fatura" in emails[0].corpo


def test_ler_nao_lidos_sem_emails():
    conn_mock = _mock_imap([], b"")
    conn_mock.search.return_value = ("OK", [b""])

    with patch("src.email_reader.imaplib.IMAP4_SSL", return_value=conn_mock):
        reader = EmailReader("imap.gmail.com", "user@test.com", "senha")
        emails = reader.ler_nao_lidos()

    assert emails == []


def test_ler_nao_lidos_detecta_anexo():
    msg_bytes = _fazer_msg(assunto="Documento", corpo="Segue documento", com_anexo=True)
    conn_mock = _mock_imap([b"1"], msg_bytes)

    with patch("src.email_reader.imaplib.IMAP4_SSL", return_value=conn_mock):
        reader = EmailReader("imap.gmail.com", "user@test.com", "senha")
        emails = reader.ler_nao_lidos()

    assert emails[0].tem_anexo is True


def test_ler_nao_lidos_sem_anexo():
    msg_bytes = _fazer_msg(assunto="Texto simples", corpo="Sem arquivo")
    conn_mock = _mock_imap([b"1"], msg_bytes)

    with patch("src.email_reader.imaplib.IMAP4_SSL", return_value=conn_mock):
        reader = EmailReader("imap.gmail.com", "user@test.com", "senha")
        emails = reader.ler_nao_lidos()

    assert emails[0].tem_anexo is False


def test_imap_erro_levanta_excecao():
    conn_mock = MagicMock()
    conn_mock.login.side_effect = imaplib.IMAP4.error("auth failed")

    with patch("src.email_reader.imaplib.IMAP4_SSL", return_value=conn_mock):
        reader = EmailReader("imap.gmail.com", "user@test.com", "senha_errada")
        with pytest.raises(imaplib.IMAP4.error):
            reader.ler_nao_lidos()

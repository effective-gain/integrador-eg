"""
Leitor de e-mails via IMAP (Gmail).
Responsabilidade única: conectar, ler e parsear e-mails. Sem Claude aqui.
"""
import email
import imaplib
import logging
import re
from datetime import datetime
from email.header import decode_header
from email.message import Message

from .models import EmailEntrada

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

_REGEX_2FA = re.compile(
    r"\b(\d{4,8})\b",
    re.IGNORECASE,
)


def _decodificar_header(valor: str | None) -> str:
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = []
    for parte, charset in partes:
        if isinstance(parte, bytes):
            resultado.append(parte.decode(charset or "utf-8", errors="replace"))
        else:
            resultado.append(parte)
    return " ".join(resultado)


def _extrair_corpo(msg: Message) -> str:
    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    corpo += payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            corpo = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return corpo.strip()


def _tem_anexo(msg: Message) -> bool:
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            return True
    return False


def extrair_codigo_2fa(texto: str) -> str | None:
    """
    Extrai código numérico de 4-8 dígitos de texto de e-mail de verificação.
    Prioriza códigos isolados (não parte de telefone/CEP).
    """
    candidatos = _REGEX_2FA.findall(texto)
    for cod in candidatos:
        # Ignora sequências muito comuns (anos, portas de rede óbvias)
        if cod in {"2024", "2025", "2026", "8080", "3000", "4000", "5000"}:
            continue
        return cod
    return None


class EmailReader:
    def __init__(self, imap_host: str, usuario: str, senha: str):
        self.imap_host = imap_host
        self.usuario = usuario
        self.senha = senha

    def _conectar(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.imap_host, IMAP_PORT)
        conn.login(self.usuario, self.senha)
        return conn

    def ler_nao_lidos(self, pasta: str = "INBOX", limite: int = 20) -> list[EmailEntrada]:
        """Retorna até `limite` e-mails não lidos da pasta."""
        try:
            conn = self._conectar()
            conn.select(pasta, readonly=True)
            _, uids_raw = conn.search(None, "UNSEEN")
            uids = uids_raw[0].split()[-limite:]

            emails = []
            for uid in uids:
                _, data = conn.fetch(uid, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                emails.append(self._parsear(uid.decode(), msg))

            conn.logout()
            logger.info("Lidos %d e-mails não lidos de '%s'", len(emails), pasta)
            return emails
        except imaplib.IMAP4.error as e:
            logger.error("Erro IMAP: %s", e)
            raise

    def buscar_por_assunto(self, pattern: str, pasta: str = "INBOX", limite: int = 5) -> list[EmailEntrada]:
        """Busca e-mails cujo assunto contenha `pattern` (útil para 2FA)."""
        try:
            conn = self._conectar()
            conn.select(pasta, readonly=True)
            criterio = f'SUBJECT "{pattern}"'
            _, uids_raw = conn.search(None, criterio)
            uids = uids_raw[0].split()[-limite:]

            emails = []
            for uid in uids:
                _, data = conn.fetch(uid, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                emails.append(self._parsear(uid.decode(), msg))

            conn.logout()
            return emails
        except imaplib.IMAP4.error as e:
            logger.error("Erro IMAP busca '%s': %s", pattern, e)
            raise

    def _parsear(self, uid: str, msg: Message) -> EmailEntrada:
        data_str = msg.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            data = parsedate_to_datetime(data_str)
        except Exception:
            data = datetime.now()

        return EmailEntrada(
            uid=uid,
            remetente=_decodificar_header(msg.get("From", "")),
            assunto=_decodificar_header(msg.get("Subject", "(sem assunto)")),
            corpo=_extrair_corpo(msg),
            data=data,
            tem_anexo=_tem_anexo(msg),
        )

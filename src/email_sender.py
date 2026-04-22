"""
Módulo de envio de e-mail do Integrador EG.

Usa Gmail SMTP com App Password (mesmo usuário do leitor IMAP).
Suporta: texto puro, HTML, templates pré-definidos (invoice, pergunta, proposta, follow-up).
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Templates HTML ─────────────────────────────────────────────────────────

_HTML_BASE = """\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  body  {{ font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:0; }}
  .wrap {{ max-width:600px; margin:32px auto; background:#fff; border-radius:8px;
           box-shadow:0 2px 8px rgba(0,0,0,.08); overflow:hidden; }}
  .header {{ background:#7c3aed; padding:24px 32px; }}
  .header h1 {{ color:#fff; margin:0; font-size:20px; font-weight:700; }}
  .header p  {{ color:#e9d5ff; margin:4px 0 0; font-size:13px; }}
  .body  {{ padding:32px; color:#374151; line-height:1.6; }}
  .body p  {{ margin:0 0 16px; }}
  .body h2 {{ font-size:16px; color:#111827; margin:0 0 12px; }}
  .footer {{ background:#f9fafb; border-top:1px solid #e5e7eb;
             padding:16px 32px; font-size:12px; color:#9ca3af; }}
  .btn {{ display:inline-block; background:#7c3aed; color:#fff; padding:10px 24px;
          border-radius:6px; text-decoration:none; font-weight:600; margin:16px 0; }}
  table {{ width:100%; border-collapse:collapse; margin:16px 0; }}
  th    {{ background:#f3f4f6; text-align:left; padding:8px 12px;
           font-size:12px; text-transform:uppercase; color:#6b7280; }}
  td    {{ padding:10px 12px; border-bottom:1px solid #f3f4f6; font-size:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>Effective Gain</h1>
    <p>Sistema de automação Integrador EG</p>
  </div>
  <div class="body">
    {conteudo}
  </div>
  <div class="footer">
    Este e-mail foi enviado automaticamente pelo Integrador EG em {data}.<br/>
    Effective Gain · info@effectivegain.com
  </div>
</div>
</body>
</html>
"""


def _template_invoice(dados: dict) -> tuple[str, str]:
    """Retorna (texto_puro, html) para invoice."""
    cliente   = dados.get("cliente", "Cliente")
    valor     = dados.get("valor", "")
    descricao = dados.get("descricao", "")
    vencimento= dados.get("vencimento", "")
    numero    = dados.get("numero", "")
    remetente = dados.get("remetente", "Effective Gain")

    texto = f"""Olá {cliente},

Segue em anexo a invoice{f' nº {numero}' if numero else ''} referente a:
{descricao}

Valor: {valor}
{f'Vencimento: {vencimento}' if vencimento else ''}

Em caso de dúvidas, responda este e-mail.

Atenciosamente,
{remetente}
"""

    html_corpo = f"""
<h2>Invoice{f' Nº {numero}' if numero else ''}</h2>
<p>Olá <strong>{cliente}</strong>,</p>
<p>Segue o detalhamento da invoice:</p>
<table>
  <tr><th>Descrição</th><th>Valor</th></tr>
  <tr><td>{descricao}</td><td><strong>{valor}</strong></td></tr>
</table>
{f'<p>Vencimento: <strong>{vencimento}</strong></p>' if vencimento else ''}
<p>Em caso de dúvidas, responda este e-mail.</p>
<p>Atenciosamente,<br/><strong>{remetente}</strong></p>
"""
    return texto, _HTML_BASE.format(conteudo=html_corpo, data=datetime.now().strftime("%d/%m/%Y %H:%M"))


def _template_pergunta(dados: dict) -> tuple[str, str]:
    """Retorna (texto_puro, html) para pergunta/consulta."""
    destinatario = dados.get("destinatario", "")
    pergunta     = dados.get("pergunta", dados.get("corpo", ""))
    remetente    = dados.get("remetente", "Effective Gain")

    texto = f"""Olá{f' {destinatario}' if destinatario else ''},

{pergunta}

Atenciosamente,
{remetente}
"""
    html_corpo = f"""
{f'<p>Olá <strong>{destinatario}</strong>,</p>' if destinatario else '<p>Olá,</p>'}
<p>{pergunta.replace(chr(10), '<br/>')}</p>
<p>Atenciosamente,<br/><strong>{remetente}</strong></p>
"""
    return texto, _HTML_BASE.format(conteudo=html_corpo, data=datetime.now().strftime("%d/%m/%Y %H:%M"))


def _template_personalizado(dados: dict) -> tuple[str, str]:
    """Template genérico — usa o corpo diretamente."""
    corpo     = dados.get("corpo", "")
    remetente = dados.get("remetente", "Effective Gain")

    texto = f"{corpo}\n\nAtenciosamente,\n{remetente}"
    html_corpo = f"""
<p>{corpo.replace(chr(10), '<br/>')}</p>
<p>Atenciosamente,<br/><strong>{remetente}</strong></p>
"""
    return texto, _HTML_BASE.format(conteudo=html_corpo, data=datetime.now().strftime("%d/%m/%Y %H:%M"))


TEMPLATES = {
    "invoice":    _template_invoice,
    "pergunta":   _template_pergunta,
    "proposta":   _template_personalizado,
    "follow_up":  _template_personalizado,
    "personalizado": _template_personalizado,
}


# ── EmailSender ────────────────────────────────────────────────────────────

class EmailSender:
    """
    Envia e-mails via SMTP (Gmail com App Password).

    Uso:
        sender = EmailSender(usuario="info@effectivegain.com", senha_app="xxxx")
        ok = await sender.enviar(
            para="cliente@empresa.com",
            assunto="Invoice mensal",
            corpo="Olá, segue invoice...",
        )
    """

    def __init__(self, usuario: str, senha_app: str,
                 smtp_host: str = "smtp.gmail.com", smtp_port: int = 587):
        self.usuario   = usuario
        self.senha_app = senha_app
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    # ── público ────────────────────────────────────────────────────────────

    async def enviar(
        self,
        para: str | list[str],
        assunto: str,
        corpo: str,
        corpo_html: str | None = None,
        reply_to: str | None = None,
    ) -> bool:
        """Envia e-mail simples (texto + html opcional)."""
        destinatarios = _normalizar_para(para)
        if not destinatarios:
            logger.warning("email_sender.enviar: nenhum destinatário válido")
            return False
        try:
            await asyncio.to_thread(
                self._enviar_sync, destinatarios, assunto, corpo, corpo_html, reply_to
            )
            logger.info("E-mail enviado para %s | assunto: %s", destinatarios, assunto)
            return True
        except Exception as e:
            logger.error("Falha ao enviar e-mail: %s", e)
            return False

    async def enviar_com_template(
        self,
        para: str | list[str],
        assunto: str,
        tipo: str,
        dados: dict,
        reply_to: str | None = None,
    ) -> bool:
        """Envia e-mail usando template pré-definido."""
        fn = TEMPLATES.get(tipo, _template_personalizado)
        corpo_texto, corpo_html = fn(dados)
        return await self.enviar(para, assunto, corpo_texto, corpo_html, reply_to)

    async def health_check(self) -> bool:
        """Verifica se as credenciais SMTP estão funcionando."""
        if not self.usuario or not self.senha_app:
            return False
        try:
            def _check():
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=8) as s:
                    s.ehlo()
                    s.starttls()
                    s.login(self.usuario, self.senha_app)
            await asyncio.to_thread(_check)
            return True
        except Exception:
            return False

    # ── privado ────────────────────────────────────────────────────────────

    def _enviar_sync(
        self,
        para: list[str],
        assunto: str,
        corpo_texto: str,
        corpo_html: str | None,
        reply_to: str | None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = f"Effective Gain <{self.usuario}>"
        msg["To"]      = ", ".join(para)
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
        if corpo_html:
            msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(self.usuario, self.senha_app)
            server.sendmail(self.usuario, para, msg.as_bytes())


# ── helpers ────────────────────────────────────────────────────────────────

def _normalizar_para(para: str | list[str]) -> list[str]:
    """Normaliza destinatários em lista de strings limpas."""
    if isinstance(para, list):
        return [p.strip() for p in para if p.strip()]
    return [p.strip() for p in str(para).split(",") if p.strip()]

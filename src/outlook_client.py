"""
Cliente Microsoft Graph API — Outlook / Microsoft 365.

Funcionalidades:
  - Enviar e-mail (com CC, BCC, importância, Reply-To, HTML)
  - Criar e enviar rascunho
  - Responder e-mail (reply / reply-all)
  - Encaminhar e-mail
  - Listar, buscar e ler mensagens
  - Mover para pasta
  - Marcar como lido / importante
  - Listar pastas
  - Verificar saúde da conexão

Autenticação: Client Credentials (app-only) via Azure AD.
Configurar no Azure Portal:
  1. Registrar app em portal.azure.com → Azure AD → App registrations
  2. API permissions → Microsoft Graph → Application → Mail.Send + Mail.ReadWrite
  3. Conceder admin consent
  4. Certificates & secrets → New client secret

Variáveis de ambiente necessárias:
  OUTLOOK_CLIENT_ID     → Application (client) ID
  OUTLOOK_CLIENT_SECRET → Client secret value
  OUTLOOK_TENANT_ID     → Directory (tenant) ID  (ou "common" para pessoal)
  OUTLOOK_USER_EMAIL    → e-mail do usuário que envia/lê (ex: info@effectivegain.com)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Importância Outlook
IMPORTANCIA = {"alta": "high", "normal": "normal", "baixa": "low",
               "high": "high", "low": "low"}

# Pastas-padrão do Outlook (Graph API usa IDs bem-conhecidos)
PASTA_ID: dict[str, str] = {
    "inbox":    "inbox",
    "caixa de entrada": "inbox",
    "enviados": "sentitems",
    "sent":     "sentitems",
    "rascunhos":"drafts",
    "lixeira":  "deleteditems",
    "spam":     "junkemail",
    "arquivo":  "archive",
}


# ── HTML Templates Outlook-compatible ──────────────────────────────────────
# Usa tables + inline styles (compatível com Outlook 2010-2021 e Outlook.com)

_HTML_BASE = """<!DOCTYPE html>
<html xmlns:v="urn:schemas-microsoft-com:vml"
      xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns:m="http://schemas.microsoft.com/office/2004/12/omml"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<!--[if mso]>
<xml><o:OfficeDocumentSettings>
<o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings></xml>
<![endif]-->
<style>
  body, table, td {{ font-family: Calibri, Arial, sans-serif; margin:0; padding:0; }}
  img {{ border:0; height:auto; line-height:100%; outline:none; text-decoration:none; }}
  @media only screen and (max-width:600px) {{
    .container {{ width:100%!important; }}
  }}
</style>
</head>
<body style="background-color:#f3f2f1; margin:0; padding:20px 0;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#f3f2f1;">
<tr><td align="center" style="padding:20px 10px;">

  <table cellpadding="0" cellspacing="0" border="0" width="600" class="container"
         style="background-color:#ffffff; border-radius:4px;
                box-shadow:0 1px 3px rgba(0,0,0,0.12); overflow:hidden;">

    <!-- Cabeçalho -->
    <tr>
      <td style="background-color:#0078d4; padding:20px 30px;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td>
              <div style="font-size:20px; font-weight:700; color:#ffffff;
                          font-family:Calibri,Arial,sans-serif; letter-spacing:-0.5px;">
                Effective Gain
              </div>
              <div style="font-size:12px; color:#b3d6f5; margin-top:3px;
                          font-family:Calibri,Arial,sans-serif;">
                {subtitulo}
              </div>
            </td>
            <td align="right" valign="middle">
              <div style="font-size:24px; background:#ffffff20; border-radius:50%;
                          width:44px; height:44px; line-height:44px; text-align:center;">
                {icone}
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Corpo -->
    <tr>
      <td style="padding:32px 30px; color:#323130;
                 font-family:Calibri,Arial,sans-serif; font-size:15px; line-height:1.6;">
        {conteudo}
      </td>
    </tr>

    <!-- Rodapé -->
    <tr>
      <td style="background-color:#f3f2f1; border-top:1px solid #edebe9;
                 padding:16px 30px;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td style="font-size:12px; color:#605e5c; font-family:Calibri,Arial,sans-serif;">
              Effective Gain · {data} · info@effectivegain.com
            </td>
            <td align="right">
              <span style="font-size:11px; color:#a19f9d;">Integrador EG</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

  </table>
</td></tr>
</table>
</body>
</html>"""

_TABELA_LINHA = """
<tr>
  <td style="padding:8px 0; border-bottom:1px solid #edebe9;
             font-size:13px; color:#605e5c; width:35%; vertical-align:top;">
    {chave}
  </td>
  <td style="padding:8px 0; border-bottom:1px solid #edebe9;
             font-size:14px; color:#323130; font-weight:600;">
    {valor}
  </td>
</tr>"""


def _tabela(linhas: list[tuple[str, str]]) -> str:
    rows = "".join(_TABELA_LINHA.format(chave=c, valor=v) for c, v in linhas)
    return f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">{rows}</table>'


def _paragrafo(texto: str) -> str:
    return f'<p style="margin:0 0 12px; font-size:15px; color:#323130; line-height:1.6;">{texto}</p>'


def _destaque(texto: str, cor: str = "#0078d4") -> str:
    return f'<strong style="color:{cor};">{texto}</strong>'


def _data_formatada() -> str:
    return datetime.now().strftime("%d/%m/%Y às %H:%M")


# ── Templates por tipo ──────────────────────────────────────────────────────

def _html_invoice(d: dict) -> tuple[str, str]:
    cliente   = d.get("cliente", "Cliente")
    valor     = d.get("valor", "—")
    descricao = d.get("descricao", "—")
    numero    = d.get("numero", "")
    vencimento= d.get("vencimento", "")
    remetente = d.get("remetente", "Effective Gain")

    titulo_num = f"Invoice Nº {numero}" if numero else "Invoice"

    linhas = [("Descrição dos serviços", descricao), ("Valor total", _destaque(valor))]
    if vencimento:
        linhas.append(("Vencimento", vencimento))

    conteudo = (
        _paragrafo(f"Olá {_destaque(cliente)},")
        + _paragrafo(f"Segue o detalhamento da {titulo_num} referente aos serviços prestados:")
        + _tabela(linhas)
        + _paragrafo("Para dúvidas ou confirmação de pagamento, responda este e-mail.")
        + _paragrafo(f"Atenciosamente,<br/>{_destaque(remetente)}")
    )

    texto_puro = (
        f"Olá {cliente},\n\n"
        f"Segue o detalhamento da {titulo_num}:\n\n"
        f"Descrição: {descricao}\n"
        f"Valor: {valor}\n"
        + (f"Vencimento: {vencimento}\n" if vencimento else "")
        + f"\nAtenciosamente,\n{remetente}"
    )

    html = _HTML_BASE.format(
        subtitulo=titulo_num,
        icone="💰",
        conteudo=conteudo,
        data=_data_formatada(),
    )
    return texto_puro, html


def _html_pergunta(d: dict) -> tuple[str, str]:
    dest     = d.get("destinatario", d.get("cliente", ""))
    corpo    = d.get("pergunta", d.get("corpo", ""))
    remetente= d.get("remetente", "Effective Gain")

    saudacao = f"Olá {_destaque(dest)}," if dest else "Olá,"

    conteudo = (
        _paragrafo(saudacao)
        + "".join(_paragrafo(p) for p in corpo.split("\n") if p.strip())
        + _paragrafo(f"Atenciosamente,<br/>{_destaque(remetente)}")
    )

    texto_puro = f"Olá{f' {dest}' if dest else ''},\n\n{corpo}\n\nAtenciosamente,\n{remetente}"

    html = _HTML_BASE.format(
        subtitulo="Mensagem",
        icone="✉️",
        conteudo=conteudo,
        data=_data_formatada(),
    )
    return texto_puro, html


def _html_proposta(d: dict) -> tuple[str, str]:
    d.setdefault("subtitulo", "Proposta Comercial")
    d.setdefault("icone", "📋")
    return _html_generico(d)


def _html_follow_up(d: dict) -> tuple[str, str]:
    d.setdefault("subtitulo", "Follow-up")
    d.setdefault("icone", "🔔")
    return _html_generico(d)


def _html_generico(d: dict) -> tuple[str, str]:
    dest     = d.get("destinatario", d.get("cliente", ""))
    corpo    = d.get("corpo", d.get("pergunta", ""))
    remetente= d.get("remetente", "Effective Gain")
    subtitulo= d.get("subtitulo", "Mensagem")
    icone    = d.get("icone", "✉️")

    saudacao = f"Olá {_destaque(dest)}," if dest else "Olá,"

    conteudo = (
        _paragrafo(saudacao)
        + "".join(_paragrafo(p) for p in corpo.split("\n") if p.strip())
        + _paragrafo(f"Atenciosamente,<br/>{_destaque(remetente)}")
    )

    texto_puro = f"Olá{f' {dest}' if dest else ''},\n\n{corpo}\n\nAtenciosamente,\n{remetente}"

    html = _HTML_BASE.format(
        subtitulo=subtitulo, icone=icone,
        conteudo=conteudo, data=_data_formatada(),
    )
    return texto_puro, html


TEMPLATE_FNS: dict[str, Any] = {
    "invoice":       _html_invoice,
    "pergunta":      _html_pergunta,
    "proposta":      _html_proposta,
    "follow_up":     _html_follow_up,
    "personalizado": _html_generico,
}


# ── OutlookClient ───────────────────────────────────────────────────────────

class OutlookClient:
    """
    Cliente Microsoft Graph API para Outlook / Microsoft 365.

    Exemplo de uso:
        cl = OutlookClient(
            client_id="...", client_secret="...",
            tenant_id="...", user_email="info@effectivegain.com"
        )
        await cl.enviar(
            para="cliente@empresa.com",
            assunto="Invoice Janeiro",
            corpo_html="<p>Olá...</p>",
        )
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        user_email: str,
    ) -> None:
        self.client_id     = client_id
        self.client_secret = client_secret
        self.tenant_id     = tenant_id
        self.user_email    = user_email
        self._token: str | None = None
        self._token_exp: float  = 0.0

    # ── autenticação ───────────────────────────────────────────────────────

    async def _token_valido(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token

        url = TOKEN_URL.format(tenant=self.tenant_id)
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, data={
                "grant_type":    "client_credentials",
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            })
            r.raise_for_status()
            data = r.json()

        self._token     = data["access_token"]
        self._token_exp = time.time() + data.get("expires_in", 3600)
        logger.debug("Token Graph API renovado (expira em %ds)", data.get("expires_in", 3600))
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._token_valido()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{GRAPH}/users/{self.user_email}/{path}"

    # ── envio ──────────────────────────────────────────────────────────────

    async def enviar(
        self,
        para: str | list[str],
        assunto: str,
        corpo_html: str,
        corpo_texto: str = "",
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        importancia: str = "normal",
        reply_to: str | None = None,
        salvar_enviados: bool = True,
    ) -> bool:
        """Envia e-mail imediatamente."""
        payload = {
            "message": _montar_mensagem(
                para=para, assunto=assunto,
                corpo_html=corpo_html, corpo_texto=corpo_texto,
                cc=cc, bcc=bcc,
                importancia=IMPORTANCIA.get(importancia.lower(), "normal"),
                reply_to=reply_to,
            ),
            "saveToSentItems": salvar_enviados,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(
                    self._url("sendMail"),
                    json=payload, headers=await self._headers(),
                )
                r.raise_for_status()
            logger.info("E-mail enviado via Graph API | para=%s | assunto=%s", para, assunto)
            return True
        except Exception as e:
            logger.error("Graph API enviar falhou: %s", e)
            return False

    async def enviar_com_template(
        self,
        para: str | list[str],
        assunto: str,
        tipo: str,
        dados: dict,
        cc: str | list[str] | None = None,
        importancia: str = "normal",
    ) -> bool:
        """Gera HTML a partir de template e envia."""
        fn = TEMPLATE_FNS.get(tipo, _html_generico)
        corpo_texto, corpo_html = fn(dados)
        return await self.enviar(
            para=para, assunto=assunto,
            corpo_html=corpo_html, corpo_texto=corpo_texto,
            cc=cc, importancia=importancia,
        )

    async def criar_rascunho(
        self,
        para: str | list[str],
        assunto: str,
        corpo_html: str,
        corpo_texto: str = "",
        cc: str | list[str] | None = None,
    ) -> str | None:
        """Cria rascunho e retorna o ID da mensagem."""
        payload = _montar_mensagem(
            para=para, assunto=assunto,
            corpo_html=corpo_html, corpo_texto=corpo_texto,
            cc=cc,
        )
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    self._url("messages"),
                    json=payload, headers=await self._headers(),
                )
                r.raise_for_status()
            draft_id = r.json().get("id")
            logger.info("Rascunho criado: %s", draft_id)
            return draft_id
        except Exception as e:
            logger.error("Graph API criar_rascunho falhou: %s", e)
            return None

    async def enviar_rascunho(self, draft_id: str) -> bool:
        """Envia um rascunho existente."""
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    self._url(f"messages/{draft_id}/send"),
                    headers=await self._headers(),
                    content=b"",
                )
                r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Graph API enviar_rascunho falhou: %s", e)
            return False

    # ── responder / encaminhar ────────────────────────────────────────────

    async def responder(
        self,
        message_id: str,
        corpo: str,
        responder_todos: bool = False,
        corpo_html: str | None = None,
    ) -> bool:
        """Responde um e-mail (reply ou reply-all)."""
        endpoint = "replyAll" if responder_todos else "reply"
        html = corpo_html or f"<p>{corpo.replace(chr(10), '<br/>')}</p>"
        payload = {
            "message": {"body": {"contentType": "HTML", "content": html}},
            "comment": corpo,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    self._url(f"messages/{message_id}/{endpoint}"),
                    json=payload, headers=await self._headers(),
                )
                r.raise_for_status()
            logger.info("E-mail respondido: %s (todos=%s)", message_id, responder_todos)
            return True
        except Exception as e:
            logger.error("Graph API responder falhou: %s", e)
            return False

    async def encaminhar(
        self,
        message_id: str,
        para: str | list[str],
        comentario: str = "",
    ) -> bool:
        """Encaminha um e-mail para novos destinatários."""
        payload = {
            "comment": comentario,
            "toRecipients": _destinatarios(para),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    self._url(f"messages/{message_id}/forward"),
                    json=payload, headers=await self._headers(),
                )
                r.raise_for_status()
            logger.info("E-mail encaminhado: %s → %s", message_id, para)
            return True
        except Exception as e:
            logger.error("Graph API encaminhar falhou: %s", e)
            return False

    # ── leitura ────────────────────────────────────────────────────────────

    async def listar_mensagens(
        self,
        pasta: str = "inbox",
        limit: int = 20,
        apenas_nao_lidos: bool = False,
        select: str = "id,subject,from,receivedDateTime,isRead,importance,hasAttachments,bodyPreview",
    ) -> list[dict]:
        """Lista mensagens de uma pasta."""
        pasta_id = PASTA_ID.get(pasta.lower(), pasta)
        filtro   = "$filter=isRead eq false" if apenas_nao_lidos else ""
        params   = f"$top={limit}&$orderby=receivedDateTime desc&$select={select}"
        if filtro:
            params = f"{params}&{filtro}"

        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    self._url(f"mailFolders/{pasta_id}/messages?{params}"),
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return r.json().get("value", [])
        except Exception as e:
            logger.error("Graph API listar_mensagens falhou: %s", e)
            return []

    async def buscar_mensagens(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Busca e-mails por texto livre (assunto, remetente, corpo)."""
        params = (
            f"$top={limit}&$orderby=receivedDateTime desc"
            f"&$search=\"{query}\""
            "&$select=id,subject,from,receivedDateTime,isRead,bodyPreview"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    self._url(f"messages?{params}"),
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return r.json().get("value", [])
        except Exception as e:
            logger.error("Graph API buscar_mensagens falhou: %s", e)
            return []

    async def obter_mensagem(self, message_id: str) -> dict | None:
        """Retorna detalhes completos de uma mensagem."""
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    self._url(f"messages/{message_id}"),
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("Graph API obter_mensagem falhou: %s", e)
            return None

    # ── ações em mensagens ─────────────────────────────────────────────────

    async def mover(self, message_id: str, pasta_destino: str) -> bool:
        """Move mensagem para outra pasta."""
        pasta_id = PASTA_ID.get(pasta_destino.lower(), pasta_destino)
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    self._url(f"messages/{message_id}/move"),
                    json={"destinationId": pasta_id},
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Graph API mover falhou: %s", e)
            return False

    async def marcar_como_lido(self, message_id: str, lido: bool = True) -> bool:
        """Marca mensagem como lida/não lida."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.patch(
                    self._url(f"messages/{message_id}"),
                    json={"isRead": lido},
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Graph API marcar_como_lido falhou: %s", e)
            return False

    async def marcar_como_importante(self, message_id: str) -> bool:
        """Marca mensagem com importância alta."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.patch(
                    self._url(f"messages/{message_id}"),
                    json={"importance": "high"},
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Graph API marcar_como_importante falhou: %s", e)
            return False

    async def deletar(self, message_id: str) -> bool:
        """Move mensagem para Lixeira."""
        return await self.mover(message_id, "lixeira")

    # ── pastas ─────────────────────────────────────────────────────────────

    async def listar_pastas(self) -> list[dict]:
        """Retorna lista de pastas da caixa de e-mail."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    self._url("mailFolders?$top=50&$select=id,displayName,unreadItemCount,totalItemCount"),
                    headers=await self._headers(),
                )
                r.raise_for_status()
            return r.json().get("value", [])
        except Exception as e:
            logger.error("Graph API listar_pastas falhou: %s", e)
            return []

    # ── saúde ──────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verifica se as credenciais estão válidas consultando o perfil."""
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(
                    f"{GRAPH}/users/{self.user_email}?$select=mail",
                    headers=await self._headers(),
                )
                return r.status_code == 200
        except Exception:
            return False


# ── helpers internos ────────────────────────────────────────────────────────

def _destinatarios(para: str | list[str]) -> list[dict]:
    if isinstance(para, str):
        para = [p.strip() for p in para.split(",") if p.strip()]
    return [{"emailAddress": {"address": e}} for e in para]


def _montar_mensagem(
    para: str | list[str],
    assunto: str,
    corpo_html: str,
    corpo_texto: str = "",
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    importancia: str = "normal",
    reply_to: str | None = None,
) -> dict:
    msg: dict = {
        "subject": assunto,
        "importance": importancia,
        "body": {
            "contentType": "HTML",
            "content": corpo_html,
        },
        "toRecipients": _destinatarios(para),
    }
    if cc:
        msg["ccRecipients"] = _destinatarios(cc)
    if bcc:
        msg["bccRecipients"] = _destinatarios(bcc)
    if reply_to:
        msg["replyTo"] = _destinatarios(reply_to)
    return msg


# ── formatar mensagem para WhatsApp ─────────────────────────────────────────

def formatar_para_whatsapp(msg: dict, max_preview: int = 120) -> str:
    """Formata uma mensagem do Graph API para exibição no WhatsApp."""
    remetente  = msg.get("from", {}).get("emailAddress", {})
    nome       = remetente.get("name", "")
    email_rem  = remetente.get("address", "")
    assunto    = msg.get("subject", "(sem assunto)")
    preview    = msg.get("bodyPreview", "")[:max_preview]
    recebido   = msg.get("receivedDateTime", "")[:16].replace("T", " ")
    nao_lido   = "🔵" if not msg.get("isRead") else "⚪"
    importante = " ⚠️" if msg.get("importance") == "high" else ""
    anexo      = " 📎" if msg.get("hasAttachments") else ""

    return (
        f"{nao_lido}{importante}{anexo} *{assunto}*\n"
        f"De: {nome or email_rem} <{email_rem}>\n"
        f"Em: {recebido}\n"
        f"_{preview}…_"
    )

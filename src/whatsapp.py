import logging
from datetime import datetime

import httpx

from .models import MensagemEntrada

logger = logging.getLogger(__name__)


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(self, base_url: str, instance: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.instance = instance
        self.headers = {"apikey": api_key, "Content-Type": "application/json"}

    async def enviar_mensagem(self, numero: str, texto: str) -> bool:
        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {"number": numero, "text": texto}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=self.headers)
                if resp.status_code not in (200, 201):
                    raise WhatsAppError(f"Evolution API retornou {resp.status_code}: {resp.text}")
                logger.info("Mensagem enviada para %s", numero)
                return True
        except httpx.TimeoutException:
            raise WhatsAppError("Timeout ao enviar mensagem via Evolution API")
        except httpx.ConnectError:
            raise WhatsAppError("Não foi possível conectar à Evolution API")

    async def download_audio(self, media_url: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(media_url, headers=self.headers)
                if resp.status_code != 200:
                    raise WhatsAppError(f"Erro ao baixar áudio: {resp.status_code}")
                return resp.content
        except httpx.TimeoutException:
            raise WhatsAppError("Timeout ao baixar áudio")

    @staticmethod
    def parsear_webhook(payload: dict) -> MensagemEntrada | None:
        """
        Converte o payload do webhook da Evolution API em MensagemEntrada.
        Retorna None se a mensagem for do próprio bot ou não for processável.
        """
        try:
            data = payload.get("data", {})
            key = data.get("key", {})
            message = data.get("message", {})

            # ignora mensagens enviadas pelo próprio bot
            if key.get("fromMe", False):
                return None

            remote_jid = key.get("remoteJid", "")
            # só processa mensagens de grupos
            if "@g.us" not in remote_jid:
                return None

            # extrai nome do grupo
            push_name = data.get("pushName", "")
            grupo_nome = data.get("key", {}).get("remoteJid", "").split("@")[0]

            # tenta extrair nome legível do grupo da metadata
            group_metadata = payload.get("groupMetadata", {})
            if group_metadata.get("subject"):
                grupo_nome = group_metadata["subject"]

            # detecta tipo de mensagem
            if "conversation" in message:
                tipo = "text"
                conteudo = message["conversation"]
            elif "extendedTextMessage" in message:
                tipo = "text"
                conteudo = message["extendedTextMessage"]["text"]
            elif "audioMessage" in message:
                tipo = "audio"
                conteudo = ""  # será transcrito depois
            elif "documentMessage" in message:
                tipo = "document"
                conteudo = message["documentMessage"].get("caption", "")
            elif "imageMessage" in message:
                tipo = "image"
                conteudo = message["imageMessage"].get("caption", "")
            else:
                return None  # tipo não suportado

            remetente = data.get("pushName") or key.get("participant", "").split("@")[0]

            return MensagemEntrada(
                grupo_id=remote_jid,
                grupo_nome=grupo_nome,
                remetente=remetente,
                conteudo=conteudo,
                tipo_original=tipo,
                timestamp=datetime.now(),
                arquivo_url=data.get("message", {}).get("audioMessage", {}).get("url"),
            )

        except Exception as e:
            logger.warning("Erro ao parsear webhook: %s", e)
            return None

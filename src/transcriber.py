"""
Transcrição de áudio via OpenAI Whisper.
Responsabilidade única: bytes de áudio → texto transcrito.
"""
import logging
from io import BytesIO

import httpx

logger = logging.getLogger(__name__)

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"
AUDIO_MIME = "audio/ogg"


class TranscritorError(Exception):
    pass


class Transcriber:
    def __init__(self, api_key: str):
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def transcrever(self, audio_bytes: bytes, idioma: str = "pt") -> str:
        """
        Envia áudio para Whisper e retorna o texto transcrito.
        idioma: hint de idioma (pt, es, en). Whisper ainda detecta automaticamente,
        mas o hint melhora precisão.
        """
        if not audio_bytes:
            raise TranscritorError("Áudio vazio — nada para transcrever")

        audio_file = BytesIO(audio_bytes)
        audio_file.name = "audio.ogg"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    WHISPER_URL,
                    headers=self.headers,
                    files={"file": ("audio.ogg", audio_file, AUDIO_MIME)},
                    data={"model": WHISPER_MODEL, "language": idioma},
                )

            if resp.status_code != 200:
                raise TranscritorError(f"Whisper retornou {resp.status_code}: {resp.text[:200]}")

            texto = resp.json().get("text", "").strip()
            if not texto:
                raise TranscritorError("Whisper retornou texto vazio")

            logger.info("Transcrição OK: %d chars", len(texto))
            return texto

        except httpx.TimeoutException:
            raise TranscritorError("Timeout na transcrição (áudio muito longo?)")
        except httpx.ConnectError:
            raise TranscritorError("Não foi possível conectar à API OpenAI")

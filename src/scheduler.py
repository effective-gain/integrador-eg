"""
Scheduler do briefing matinal usando APScheduler (asyncio).
Dispara todo dia no horário configurado via BRIEFING_HORA.
"""
import asyncio
import logging

import anthropic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .briefing import coletar_briefing_data, formatar_briefing_whatsapp
from .email_reader import EmailReader
from .obsidian import ObsidianClient

logger = logging.getLogger(__name__)


class BriefingScheduler:
    def __init__(
        self,
        obsidian: ObsidianClient,
        whatsapp_send_fn,           # callable async (numero: str, texto: str) -> None
        numero_destino: str,
        hora: str = "08:00",        # formato HH:MM
        email_reader: EmailReader | None = None,
        anthropic_client: anthropic.Anthropic | None = None,
    ):
        self.obsidian = obsidian
        self.whatsapp_send_fn = whatsapp_send_fn
        self.numero_destino = numero_destino
        self.email_reader = email_reader
        self.anthropic_client = anthropic_client

        hora_str, minuto_str = hora.split(":")
        self._hora = int(hora_str)
        self._minuto = int(minuto_str)

        self._scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    def iniciar(self) -> None:
        self._scheduler.add_job(
            self._executar_briefing,
            trigger=CronTrigger(hour=self._hora, minute=self._minuto),
            id="briefing_matinal",
            name="Briefing matinal EG",
            replace_existing=True,
            misfire_grace_time=300,  # tolera até 5min de atraso
        )
        self._scheduler.start()
        logger.info(
            "Briefing agendado para %02d:%02d (America/Sao_Paulo) → %s",
            self._hora, self._minuto, self.numero_destino,
        )

    def parar(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler parado.")

    async def _executar_briefing(self) -> None:
        logger.info("Iniciando geração do briefing matinal...")
        try:
            dados = await coletar_briefing_data(
                obsidian=self.obsidian,
                email_reader=self.email_reader,
                anthropic_client=self.anthropic_client,
            )
            texto = formatar_briefing_whatsapp(dados)
            await self.whatsapp_send_fn(self.numero_destino, texto)
            logger.info("Briefing enviado para %s (%d chars)", self.numero_destino, len(texto))
        except Exception as e:
            logger.error("FALHA no briefing matinal: %s", e, exc_info=True)
            # Nunca deixa o scheduler morrer por erro no job

"""
Controle de status do bot por grupo WhatsApp (Postgres async).

Permite pausar/reativar o bot em grupos específicos via comandos:
  /pausar        — pausa indefinidamente
  /pausar 2h     — pausa por 2 horas
  /pausar 30m    — pausa por 30 minutos
  /pausar 1h30m  — pausa por 1h30m
  /ativar        — reativa imediatamente
  /status        — mostra estado atual do bot no grupo

Migrado de SQLite síncrono para Postgres async (asyncpg) para não
bloquear o event loop do FastAPI e sobreviver a restarts de container.
"""

import logging
import re
from datetime import datetime, timedelta

from src.db import get_pool

logger = logging.getLogger(__name__)

# Comandos reconhecidos (case-insensitive, com ou sem barra)
PREFIXOS_COMANDO = ("/pausar", "/ativar", "/status", "/botstatus")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_status (
    grupo_id      TEXT PRIMARY KEY,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    pausado_ate   TIMESTAMPTZ,
    pausado_por   TEXT,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def parsear_comando(texto: str) -> tuple[str, int | None] | None:
    """
    Detecta se a mensagem é um comando de bot e extrai o comando e duração.

    Retorna:
        ("pausar", minutos | None)  — para /pausar
        ("ativar", None)            — para /ativar
        ("status", None)            — para /status ou /botstatus
        None                        — não é um comando de bot
    """
    t = texto.strip().lower()

    if t.startswith("/ativar"):
        return ("ativar", None)

    if t in ("/status", "/botstatus"):
        return ("status", None)

    if t.startswith("/pausar"):
        resto = t[len("/pausar"):].strip()
        if not resto:
            return ("pausar", None)
        minutos = _parsear_duracao(resto)
        return ("pausar", minutos)

    return None


def _parsear_duracao(texto: str) -> int | None:
    """Converte strings como '2h', '30m', '1h30m' em minutos."""
    texto = texto.lower().strip()
    horas = re.search(r"(\d+)h", texto)
    mins = re.search(r"(\d+)m(?!in)", texto)
    total = 0
    if horas:
        total += int(horas.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    return total if total > 0 else None


class BotStatus:
    """Controla se o bot está ativo ou pausado por grupo WhatsApp (Postgres async)."""

    # ── consulta ───────────────────────────────────────────────────────────

    async def ativo(self, grupo_id: str) -> bool:
        """Retorna True se o bot está ativo neste grupo (auto-reativa quando TTL expira)."""
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT ativo, pausado_ate FROM bot_status WHERE grupo_id = $1",
            grupo_id,
        )

        if row is None:
            return True  # sem registro → ativo por padrão

        ativo, pausado_ate = row["ativo"], row["pausado_ate"]
        if not ativo and pausado_ate:
            if datetime.now(pausado_ate.tzinfo) >= pausado_ate:
                await self._setar_ativo(grupo_id)
                logger.info("Bot auto-reativado por TTL | grupo=%s", grupo_id)
                return True

        return bool(ativo)

    async def status_texto(self, grupo_id: str) -> str:
        """Retorna texto legível com o status atual do bot no grupo."""
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT ativo, pausado_ate, pausado_por FROM bot_status WHERE grupo_id = $1",
            grupo_id,
        )

        if row is None or row["ativo"]:
            return "✅ Bot ativo e pronto para receber comandos."

        pausado_ate = row["pausado_ate"]
        pausado_por = row["pausado_por"]

        if pausado_ate:
            ate = pausado_ate.astimezone()
            return (
                f"⏸️ Bot pausado até {ate.strftime('%d/%m às %H:%M')}.\n"
                f"Use /ativar para reativar antes do prazo."
            )
        quem = f" por {pausado_por}" if pausado_por else ""
        return f"⏸️ Bot pausado{quem} indefinidamente.\nUse /ativar para reativar."

    # ── ações ──────────────────────────────────────────────────────────────

    async def pausar(self, grupo_id: str, minutos: int | None = None, por: str = "") -> str:
        """Pausa o bot. Se minutos=None, pausa indefinidamente."""
        pausado_ate = None
        if minutos:
            pausado_ate = datetime.now() + timedelta(minutes=minutos)

        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO bot_status (grupo_id, ativo, pausado_ate, pausado_por, atualizado_em)
            VALUES ($1, FALSE, $2, $3, NOW())
            ON CONFLICT (grupo_id) DO UPDATE SET
                ativo         = FALSE,
                pausado_ate   = EXCLUDED.pausado_ate,
                pausado_por   = EXCLUDED.pausado_por,
                atualizado_em = NOW()
            """,
            grupo_id, pausado_ate, por or None,
        )

        logger.info("Bot pausado | grupo=%s | minutos=%s | por=%s", grupo_id, minutos, por)

        if minutos:
            h, m = divmod(minutos, 60)
            duracao = f"{h}h{m:02d}m" if h and m else (f"{h}h" if h else f"{m}m")
            return (
                f"⏸️ Bot pausado por *{duracao}*.\n"
                f"Use /ativar para reativar antes do prazo."
            )
        return "⏸️ Bot pausado indefinidamente.\nUse /ativar quando quiser reativar."

    async def ativar(self, grupo_id: str) -> str:
        """Reativa o bot para um grupo."""
        await self._setar_ativo(grupo_id)
        logger.info("Bot ativado | grupo=%s", grupo_id)
        return "▶️ Bot reativado! Pode enviar comandos normalmente."

    # ── interno ────────────────────────────────────────────────────────────

    async def _setar_ativo(self, grupo_id: str) -> None:
        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO bot_status (grupo_id, ativo, pausado_ate, pausado_por, atualizado_em)
            VALUES ($1, TRUE, NULL, NULL, NOW())
            ON CONFLICT (grupo_id) DO UPDATE SET
                ativo         = TRUE,
                pausado_ate   = NULL,
                pausado_por   = NULL,
                atualizado_em = NOW()
            """,
            grupo_id,
        )

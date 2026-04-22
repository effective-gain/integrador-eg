"""
Controle de status do bot por grupo WhatsApp.

Permite pausar/reativar o bot em grupos específicos via comandos:
  /pausar        — pausa indefinidamente
  /pausar 2h     — pausa por 2 horas
  /pausar 30m    — pausa por 30 minutos
  /pausar 1h30m  — pausa por 1h30m
  /ativar        — reativa imediatamente
  /status        — mostra estado atual do bot no grupo
"""

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/bot_status.db")

# Comandos reconhecidos (case-insensitive, com ou sem barra)
PREFIXOS_COMANDO = ("/pausar", "/ativar", "/status", "/botstatus")


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
    """Controla se o bot está ativo ou pausado por grupo WhatsApp (SQLite)."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── setup ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_status (
                    grupo_id      TEXT PRIMARY KEY,
                    ativo         INTEGER NOT NULL DEFAULT 1,
                    pausado_ate   TEXT,
                    pausado_por   TEXT,
                    atualizado_em TEXT NOT NULL
                )
            """)

    # ── consulta ───────────────────────────────────────────────────────────

    def ativo(self, grupo_id: str) -> bool:
        """Retorna True se o bot está ativo neste grupo (auto-reativa quando TTL expira)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT ativo, pausado_ate FROM bot_status WHERE grupo_id = ?",
                (grupo_id,),
            ).fetchone()

        if row is None:
            return True  # sem registro → ativo por padrão

        ativo, pausado_ate = row
        if not ativo and pausado_ate:
            if datetime.now() >= datetime.fromisoformat(pausado_ate):
                self._setar_ativo(grupo_id)
                logger.info("Bot auto-reativado por TTL | grupo=%s", grupo_id)
                return True

        return bool(ativo)

    def status_texto(self, grupo_id: str) -> str:
        """Retorna texto legível com o status atual do bot no grupo."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT ativo, pausado_ate, pausado_por FROM bot_status WHERE grupo_id = ?",
                (grupo_id,),
            ).fetchone()

        if row is None or row[0]:
            return "✅ Bot ativo e pronto para receber comandos."

        _, pausado_ate, pausado_por = row
        if pausado_ate:
            ate = datetime.fromisoformat(pausado_ate)
            return (
                f"⏸️ Bot pausado até {ate.strftime('%d/%m às %H:%M')}.\n"
                f"Use /ativar para reativar antes do prazo."
            )
        quem = f" por {pausado_por}" if pausado_por else ""
        return f"⏸️ Bot pausado{quem} indefinidamente.\nUse /ativar para reativar."

    # ── ações ──────────────────────────────────────────────────────────────

    def pausar(self, grupo_id: str, minutos: int | None = None, por: str = "") -> str:
        """Pausa o bot. Se minutos=None, pausa indefinidamente."""
        pausado_ate = None
        if minutos:
            pausado_ate = (datetime.now() + timedelta(minutes=minutos)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO bot_status (grupo_id, ativo, pausado_ate, pausado_por, atualizado_em)
                VALUES (?, 0, ?, ?, ?)
                ON CONFLICT(grupo_id) DO UPDATE SET
                    ativo         = 0,
                    pausado_ate   = excluded.pausado_ate,
                    pausado_por   = excluded.pausado_por,
                    atualizado_em = excluded.atualizado_em
            """, (grupo_id, pausado_ate, por or None, datetime.now().isoformat()))

        logger.info("Bot pausado | grupo=%s | minutos=%s | por=%s", grupo_id, minutos, por)

        if minutos:
            h, m = divmod(minutos, 60)
            duracao = f"{h}h{m:02d}m" if h and m else (f"{h}h" if h else f"{m}m")
            return (
                f"⏸️ Bot pausado por *{duracao}*.\n"
                f"Use /ativar para reativar antes do prazo."
            )
        return "⏸️ Bot pausado indefinidamente.\nUse /ativar quando quiser reativar."

    def ativar(self, grupo_id: str) -> str:
        """Reativa o bot para um grupo."""
        self._setar_ativo(grupo_id)
        logger.info("Bot ativado | grupo=%s", grupo_id)
        return "▶️ Bot reativado! Pode enviar comandos normalmente."

    # ── interno ────────────────────────────────────────────────────────────

    def _setar_ativo(self, grupo_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO bot_status (grupo_id, ativo, pausado_ate, pausado_por, atualizado_em)
                VALUES (?, 1, NULL, NULL, ?)
                ON CONFLICT(grupo_id) DO UPDATE SET
                    ativo         = 1,
                    pausado_ate   = NULL,
                    pausado_por   = NULL,
                    atualizado_em = excluded.atualizado_em
            """, (grupo_id, datetime.now().isoformat()))

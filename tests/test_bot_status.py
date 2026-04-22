"""Testa BotStatus (on/off do bot por grupo) e parsear_comando."""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.bot_status import BotStatus, parsear_comando


# ── parsear_comando ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("/pausar",         ("pausar", None)),
    ("/pausar 2h",      ("pausar", 120)),
    ("/pausar 30m",     ("pausar", 30)),
    ("/pausar 1h30m",   ("pausar", 90)),
    ("/pausar 1h",      ("pausar", 60)),
    ("/ativar",         ("ativar", None)),
    ("/status",         ("status", None)),
    ("/botstatus",      ("status", None)),
    # não são comandos
    ("registrar nota",  None),
    ("pausar reunião",  None),
    ("criar task",      None),
    ("",               None),
])
def test_parsear_comando(texto, esperado):
    assert parsear_comando(texto) == esperado


# ── BotStatus ──────────────────────────────────────────────────────────────────

@pytest.fixture
def bot(tmp_path):
    return BotStatus(db_path=tmp_path / "bot_status.db")


def test_bot_ativo_por_padrao(bot):
    assert bot.ativo("grupo-1") is True


def test_pausar_indefinidamente(bot):
    msg = bot.pausar("grupo-1")
    assert bot.ativo("grupo-1") is False
    assert "indefinidamente" in msg.lower()


def test_pausar_com_duracao(bot):
    msg = bot.pausar("grupo-1", minutos=60)
    assert bot.ativo("grupo-1") is False
    assert "1h" in msg


def test_ativar_apos_pausa(bot):
    bot.pausar("grupo-1")
    msg = bot.ativar("grupo-1")
    assert bot.ativo("grupo-1") is True
    assert "reativado" in msg.lower()


def test_auto_reativacao_por_ttl(bot):
    """Bot pausado por 1 minuto deve ser auto-reativado quando o TTL expira."""
    # Pausa por 1 minuto
    bot.pausar("grupo-1", minutos=1)
    assert bot.ativo("grupo-1") is False

    # Simula TTL expirado alterando diretamente o DB
    import sqlite3
    passado = (datetime.now() - timedelta(minutes=2)).isoformat()
    with sqlite3.connect(bot.db_path) as conn:
        conn.execute(
            "UPDATE bot_status SET pausado_ate = ? WHERE grupo_id = ?",
            (passado, "grupo-1"),
        )

    # Agora deve auto-reativar
    assert bot.ativo("grupo-1") is True


def test_status_texto_ativo(bot):
    texto = bot.status_texto("grupo-novo")
    assert "ativo" in texto.lower()


def test_status_texto_pausado_indefinido(bot):
    bot.pausar("grupo-1")
    texto = bot.status_texto("grupo-1")
    assert "pausado" in texto.lower()
    assert "/ativar" in texto


def test_status_texto_pausado_com_prazo(bot):
    bot.pausar("grupo-1", minutos=120)
    texto = bot.status_texto("grupo-1")
    assert "pausado" in texto.lower()
    # Deve mostrar a hora de retorno
    assert ":" in texto  # formato HH:MM


def test_multiplos_grupos_independentes(bot):
    bot.pausar("grupo-A")
    assert bot.ativo("grupo-A") is False
    assert bot.ativo("grupo-B") is True  # não afeta outros grupos


def test_pausa_por_remetente(bot):
    """O campo 'por' deve ser armazenado e aparecer no status."""
    bot.pausar("grupo-1", por="Luiz")
    texto = bot.status_texto("grupo-1")
    assert "Luiz" in texto or "pausado" in texto.lower()

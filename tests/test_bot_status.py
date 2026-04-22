"""Testa BotStatus (on/off do bot por grupo) — Postgres async mockado."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_pool(row=None):
    """Cria um mock do asyncpg pool."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=row)
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def bot():
    return BotStatus()


# ── BotStatus.ativo ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bot_ativo_por_padrao(bot):
    """Sem registro no banco → ativo por padrão."""
    pool = _make_pool(row=None)
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        assert await bot.ativo("grupo-1") is True


@pytest.mark.asyncio
async def test_bot_ativo_quando_registro_ativo(bot):
    pool = _make_pool(row={"ativo": True, "pausado_ate": None})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        assert await bot.ativo("grupo-1") is True


@pytest.mark.asyncio
async def test_bot_pausado_indefinidamente(bot):
    pool = _make_pool(row={"ativo": False, "pausado_ate": None})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        assert await bot.ativo("grupo-1") is False


@pytest.mark.asyncio
async def test_bot_pausado_sem_ttl_expirado(bot):
    futuro = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    pool = _make_pool(row={"ativo": False, "pausado_ate": futuro})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        assert await bot.ativo("grupo-1") is False


@pytest.mark.asyncio
async def test_auto_reativacao_por_ttl(bot):
    """Quando pausado_ate está no passado, deve auto-reativar."""
    passado = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    pool = _make_pool(row={"ativo": False, "pausado_ate": passado})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        resultado = await bot.ativo("grupo-1")
        assert resultado is True
        # Deve ter chamado execute para setar ativo=TRUE no banco
        pool.execute.assert_called_once()


# ── BotStatus.pausar ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pausar_indefinidamente(bot):
    pool = _make_pool()
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        msg = await bot.pausar("grupo-1")
        assert "indefinidamente" in msg.lower()
        pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_pausar_com_duracao_60m(bot):
    pool = _make_pool()
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        msg = await bot.pausar("grupo-1", minutos=60)
        assert "1h" in msg
        pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_pausar_com_duracao_90m(bot):
    pool = _make_pool()
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        msg = await bot.pausar("grupo-1", minutos=90)
        assert "1h30m" in msg


@pytest.mark.asyncio
async def test_pausar_com_duracao_30m(bot):
    pool = _make_pool()
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        msg = await bot.pausar("grupo-1", minutos=30)
        assert "30m" in msg


# ── BotStatus.ativar ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ativar(bot):
    pool = _make_pool()
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        msg = await bot.ativar("grupo-1")
        assert "reativado" in msg.lower()
        pool.execute.assert_called_once()


# ── BotStatus.status_texto ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_texto_ativo(bot):
    pool = _make_pool(row=None)  # sem registro → ativo
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        texto = await bot.status_texto("grupo-novo")
        assert "ativo" in texto.lower()


@pytest.mark.asyncio
async def test_status_texto_pausado_indefinido(bot):
    pool = _make_pool(row={"ativo": False, "pausado_ate": None, "pausado_por": None})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        texto = await bot.status_texto("grupo-1")
        assert "pausado" in texto.lower()
        assert "/ativar" in texto


@pytest.mark.asyncio
async def test_status_texto_pausado_com_prazo(bot):
    futuro = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    pool = _make_pool(row={"ativo": False, "pausado_ate": futuro, "pausado_por": None})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        texto = await bot.status_texto("grupo-1")
        assert "pausado" in texto.lower()
        assert ":" in texto  # formato HH:MM


@pytest.mark.asyncio
async def test_status_texto_pausado_com_remetente(bot):
    pool = _make_pool(row={"ativo": False, "pausado_ate": None, "pausado_por": "Luiz"})
    with patch("src.bot_status.get_pool", AsyncMock(return_value=pool)):
        texto = await bot.status_texto("grupo-1")
        assert "Luiz" in texto or "pausado" in texto.lower()

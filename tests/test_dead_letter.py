"""Testa DeadLetterQueue (Postgres async via asyncpg pool mockado)."""
import pytest
from unittest.mock import AsyncMock, patch

from src.dead_letter import DeadLetterQueue, MAX_TENTATIVAS


def _make_pool(rows=None, fetchval=0):
    """Cria um mock do asyncpg pool."""
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=fetchval)
    pool.fetch = AsyncMock(return_value=rows or [])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def dlq():
    return DeadLetterQueue()


@pytest.mark.asyncio
async def test_enfileirar_e_listar(dlq):
    mock_pool = _make_pool(fetchval=1)
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        item_id = await dlq.enfileirar("g1", "Grupo", "criar_nota", "K2Con", "## Nota", "timeout")
        assert item_id == 1
        mock_pool.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_remover_item(dlq):
    mock_pool = _make_pool()
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        await dlq.remover(42)
        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        assert "DELETE" in args[0]
        assert 42 in args


@pytest.mark.asyncio
async def test_incrementar_tentativas(dlq):
    mock_pool = _make_pool()
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        await dlq.incrementar_tentativas(5, "erro novo")
        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        assert "UPDATE" in args[0]
        assert "erro novo" in args


@pytest.mark.asyncio
async def test_total_pendentes(dlq):
    mock_pool = _make_pool(fetchval=3)
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        total = await dlq.total_pendentes()
        assert total == 3


@pytest.mark.asyncio
async def test_listar_pendentes_retorna_lista(dlq):
    mock_row = {"id": 1, "grupo_id": "g1", "acao": "criar_nota", "projeto": "K2Con",
                "conteudo_formatado": "## nota", "tentativas": 0}
    mock_pool = _make_pool(rows=[mock_row])
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        items = await dlq.listar_pendentes()
        assert len(items) == 1
        assert items[0]["acao"] == "criar_nota"


@pytest.mark.asyncio
async def test_listar_pendentes_vazia(dlq):
    mock_pool = _make_pool(rows=[])
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        items = await dlq.listar_pendentes()
        assert items == []


@pytest.mark.asyncio
async def test_enfileirar_loga_warning(dlq, caplog):
    mock_pool = _make_pool(fetchval=7)
    import logging
    with patch("src.dead_letter.get_pool", AsyncMock(return_value=mock_pool)):
        with caplog.at_level(logging.WARNING, logger="src.dead_letter"):
            await dlq.enfileirar("g1", "Grupo", "criar_nota", "K2Con", "## N", "err")
    assert "Dead letter" in caplog.text

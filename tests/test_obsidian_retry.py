"""Testa retry logic e verificar_diario_hoje do ObsidianClient."""
import pytest
import respx
import httpx
from unittest.mock import patch, AsyncMock

from src.obsidian import ObsidianClient, ObsidianError, RETRY_ATTEMPTS
from src.models import ObsidianEscrita

BASE_URL = "http://localhost:27124"


def make_client():
    return ObsidianClient(base_url=BASE_URL, api_key="test-key")


@pytest.mark.asyncio
@respx.mock
async def test_retry_sucesso_na_segunda_tentativa():
    """Falha na 1ª, sucesso na 2ª — deve retornar True sem levantar erro."""
    rota = respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md")
    rota.side_effect = [
        httpx.ConnectError("timeout"),
        httpx.Response(200),
    ]
    client = make_client()
    with patch("src.obsidian.asyncio.sleep") as mock_sleep:
        result = await client.criar_ou_append(ObsidianEscrita(
            caminho="06 - Diario/2026-04-17.md",
            conteudo="x",
            modo="append",
        ))
    assert result is True
    mock_sleep.assert_called_once()  # dormiu 1 vez (entre tentativa 1 e 2)


@pytest.mark.asyncio
@respx.mock
async def test_retry_esgota_todas_tentativas():
    """3 falhas consecutivas → ObsidianError com contagem correta."""
    respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md").mock(
        side_effect=httpx.ConnectError("refused")
    )
    client = make_client()
    with patch("src.obsidian.asyncio.sleep"):
        with pytest.raises(ObsidianError) as exc_info:
            await client.criar_ou_append(ObsidianEscrita(
                caminho="06 - Diario/2026-04-17.md",
                conteudo="x",
                modo="append",
            ))
    assert str(RETRY_ATTEMPTS) in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_retry_status_500_tenta_novamente():
    """HTTP 500 é tratado como erro recuperável e ativa retry."""
    rota = respx.post(f"{BASE_URL}/vault/nota.md")
    rota.side_effect = [
        httpx.Response(500, text="internal error"),
        httpx.Response(200),
    ]
    client = make_client()
    with patch("src.obsidian.asyncio.sleep"):
        result = await client.criar_ou_append(ObsidianEscrita(
            caminho="nota.md",
            conteudo="x",
            modo="append",
        ))
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_verificar_diario_hoje_sem_nota():
    """Diário inexistente → retorna dict com existe=False."""
    import datetime
    hoje = datetime.date.today().strftime("%Y-%m-%d")
    respx.get(f"{BASE_URL}/vault/06 - Diario/{hoje}.md").mock(
        return_value=httpx.Response(404)
    )
    client = make_client()
    resultado = await client.verificar_diario_hoje()
    assert resultado["existe"] is False
    assert resultado["entradas"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_verificar_diario_hoje_conta_entradas():
    """Diário com 3 entradas (2 sucesso, 1 erro) → contagens corretas."""
    import datetime
    hoje = datetime.date.today().strftime("%Y-%m-%d")
    conteudo = (
        "# Diário\n\n"
        "- 09:00 ✅ **criar_nota** | Gestão EG | nota sobre reunião\n"
        "- 10:00 ✅ **criar_task** | K2Con | task criada\n"
        "- 11:00 ❌ **registrar_lancamento** | Gestão EG | falhou *(erro: timeout)*\n"
    )
    respx.get(f"{BASE_URL}/vault/06 - Diario/{hoje}.md").mock(
        return_value=httpx.Response(200, text=conteudo)
    )
    client = make_client()
    resultado = await client.verificar_diario_hoje()
    assert resultado["existe"] is True
    assert resultado["entradas"] == 3
    assert resultado["sucesso"] == 2
    assert resultado["erro"] == 1
    assert resultado["ambigua"] == 0

import pytest
import respx
import httpx
from datetime import datetime
from unittest.mock import patch

from src.obsidian import ObsidianClient, ObsidianError
from src.models import AcaoTipo, DiarioEntrada, ObsidianEscrita


BASE_URL = "http://localhost:27124"
API_KEY = "test-key"


def make_client():
    return ObsidianClient(base_url=BASE_URL, api_key=API_KEY)


@pytest.mark.asyncio
@respx.mock
async def test_criar_nota_sucesso():
    respx.put(f"{BASE_URL}/vault/04 - Inbox/2026-04-17-K2Con.md").mock(return_value=httpx.Response(204))
    client = make_client()
    escrita = ObsidianEscrita(
        caminho="04 - Inbox/2026-04-17-K2Con.md",
        conteudo="## Nota\n\nconteúdo",
        modo="create",
    )
    result = await client.criar_ou_append(escrita)
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_append_nota_sucesso():
    respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md").mock(return_value=httpx.Response(200))
    client = make_client()
    escrita = ObsidianEscrita(
        caminho="06 - Diario/2026-04-17.md",
        conteudo="\n- 10:00 ✅ criar_nota",
        modo="append",
    )
    result = await client.criar_ou_append(escrita)
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_obsidian_offline_lanca_erro():
    respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    client = make_client()
    with patch("src.obsidian.asyncio.sleep"):
        with pytest.raises(ObsidianError, match="Falha após"):
            await client.criar_ou_append(ObsidianEscrita(
                caminho="06 - Diario/2026-04-17.md",
                conteudo="x",
                modo="append",
            ))


@pytest.mark.asyncio
@respx.mock
async def test_registrar_diario_formato_correto():
    captured = []

    async def capturar(request, route):
        captured.append(request.content.decode())
        return httpx.Response(200)

    respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md").mock(side_effect=capturar)

    client = make_client()
    entrada = DiarioEntrada(
        timestamp=datetime(2026, 4, 17, 10, 30),
        grupo="gestao-eg",
        projeto="Gestão EG",
        acao=AcaoTipo.CRIAR_NOTA,
        conteudo_resumo="nota sobre reunião",
        resultado="sucesso",
    )
    await client.registrar_diario(entrada)

    assert len(captured) == 1
    texto = captured[0]
    assert "10:30" in texto
    assert "criar_nota" in texto
    assert "Gestão EG" in texto
    assert "✅" in texto


@pytest.mark.asyncio
@respx.mock
async def test_registrar_diario_erro_inclui_detalhe():
    captured = []

    async def capturar(request, route):
        captured.append(request.content.decode())
        return httpx.Response(200)

    respx.post(f"{BASE_URL}/vault/06 - Diario/2026-04-17.md").mock(side_effect=capturar)

    client = make_client()
    entrada = DiarioEntrada(
        timestamp=datetime(2026, 4, 17, 14, 0),
        grupo="k2con",
        projeto="K2Con",
        acao=AcaoTipo.CRIAR_TASK,
        conteudo_resumo="task falhou",
        resultado="erro",
        erro_detalhe="timeout na plataforma",
    )
    await client.registrar_diario(entrada)
    assert "timeout na plataforma" in captured[0]
    assert "❌" in captured[0]


@pytest.mark.asyncio
@respx.mock
async def test_caminho_acao_sem_caracteres_invalidos():
    client = make_client()
    caminho = client._caminho_para_acao(AcaoTipo.CRIAR_NOTA, "Beef Smash & Co", "2026-04-17")
    assert "&" not in caminho
    assert " " not in caminho.split("/")[-1]


@pytest.mark.asyncio
@respx.mock
async def test_health_check_ok():
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200))
    client = make_client()
    assert await client.health_check() is True


@pytest.mark.asyncio
@respx.mock
async def test_health_check_offline():
    respx.get(f"{BASE_URL}/").mock(side_effect=httpx.ConnectError("offline"))
    client = make_client()
    assert await client.health_check() is False

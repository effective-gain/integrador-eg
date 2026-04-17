"""Testa o engine de receitas sem Playwright real."""
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.receita import (
    PassoReceita,
    Receita,
    ReceitaError,
    ReceitaValidacaoError,
    ResultadoReceita,
    _substituir_variaveis,
    carregar_receita,
    validar_variaveis,
)


# ── Fixture: receita de teste em arquivo temporário ──────────────────────────

@pytest.fixture
def receita_yaml_simples(tmp_path):
    conteudo = textwrap.dedent("""
        id: teste_simples
        nome: Receita de Teste
        descricao: Preenche um formulário simples
        url: "https://exemplo.com/{ambiente}"
        credenciais_chave:
          - usuario
          - senha
        passos:
          - tipo: fill
            seletor: "input#user"
            valor: "{usuario}"
            descricao: "Preenche usuário"
          - tipo: fill
            seletor: "input#pass"
            valor: "{senha}"
            descricao: "Preenche senha"
          - tipo: click
            seletor: "button#submit"
            descricao: "Submete formulário"
        saida_seletor: ".confirmation"
        saida_descricao: "Número de confirmação"
        delay_humano_ms: 0
    """)
    arquivo = tmp_path / "teste_simples.yaml"
    arquivo.write_text(conteudo, encoding="utf-8")
    return tmp_path


# ── _substituir_variaveis ─────────────────────────────────────────────────────

def test_substituir_variaveis_simples():
    assert _substituir_variaveis("Olá {nome}!", {"nome": "World"}) == "Olá World!"


def test_substituir_variaveis_multiplas():
    resultado = _substituir_variaveis("{a} + {b} = {c}", {"a": "1", "b": "2", "c": "3"})
    assert resultado == "1 + 2 = 3"


def test_substituir_variaveis_pendente_lanca_erro():
    with pytest.raises(ReceitaValidacaoError, match="Variáveis não fornecidas"):
        _substituir_variaveis("{url}/{chave_faltando}", {"url": "https://x.com"})


def test_substituir_variaveis_sem_chaves():
    assert _substituir_variaveis("texto fixo", {}) == "texto fixo"


# ── carregar_receita ──────────────────────────────────────────────────────────

def test_carregar_receita_ok(receita_yaml_simples):
    with patch("src.receita.RECEITAS_DIR", receita_yaml_simples):
        receita = carregar_receita("teste_simples")

    assert receita.id == "teste_simples"
    assert len(receita.passos) == 3
    assert receita.passos[0].tipo == "fill"
    assert receita.credenciais_chave == ["usuario", "senha"]
    assert receita.delay_humano_ms == 0


def test_carregar_receita_nao_encontrada(tmp_path):
    with patch("src.receita.RECEITAS_DIR", tmp_path):
        with pytest.raises(ReceitaError, match="não encontrada"):
            carregar_receita("inexistente")


def test_carregar_receita_campo_faltando(tmp_path):
    arquivo = tmp_path / "ruim.yaml"
    arquivo.write_text("id: ruim\nnome: Ruim\n", encoding="utf-8")
    with patch("src.receita.RECEITAS_DIR", tmp_path):
        with pytest.raises(ReceitaValidacaoError):
            carregar_receita("ruim")


# ── validar_variaveis ─────────────────────────────────────────────────────────

def _fazer_receita(credenciais=None):
    return Receita(
        id="x", nome="X", descricao="X",
        url="https://x.com",
        credenciais_chave=credenciais or ["usuario", "senha"],
        passos=[],
    )


def test_validar_variaveis_todas_presentes():
    faltando = validar_variaveis(_fazer_receita(), {"usuario": "u", "senha": "s"})
    assert faltando == []


def test_validar_variaveis_faltando_uma():
    faltando = validar_variaveis(_fazer_receita(), {"usuario": "u"})
    assert faltando == ["senha"]


def test_validar_variaveis_faltando_todas():
    faltando = validar_variaveis(_fazer_receita(), {})
    assert set(faltando) == {"usuario", "senha"}


# ── executar_receita (mock de Playwright) ────────────────────────────────────

def _fazer_receita_completa():
    return Receita(
        id="demo",
        nome="Demo",
        descricao="Demo",
        url="https://demo.com",
        credenciais_chave=["usuario"],
        passos=[
            PassoReceita(tipo="fill", seletor="input#u", valor="{usuario}"),
            PassoReceita(tipo="click", seletor="button#ok"),
        ],
        saida_seletor=".resultado",
        delay_humano_ms=0,
    )


def _montar_mock_playwright(texto_saida="CONF-1234"):
    """Monta a cadeia de mocks do Playwright."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock(return_value="<html>ok</html>")

    locator = AsyncMock()
    locator.click = AsyncMock()
    locator.clear = AsyncMock()
    locator.type = AsyncMock()
    locator.inner_text = AsyncMock(return_value=texto_saida)
    locator.wait_for = AsyncMock()
    page.locator = MagicMock(return_value=locator)

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    playwright_ctx = AsyncMock()
    playwright_ctx.__aenter__ = AsyncMock(return_value=playwright_ctx)
    playwright_ctx.__aexit__ = AsyncMock(return_value=False)
    playwright_ctx.chromium = AsyncMock()
    playwright_ctx.chromium.launch = AsyncMock(return_value=browser)

    return playwright_ctx


@pytest.mark.asyncio
async def test_executar_receita_sucesso():
    from src.receita import executar_receita
    receita = _fazer_receita_completa()
    mock_pw = _montar_mock_playwright("CONF-9999")

    with patch("src.receita.PLAYWRIGHT_DISPONIVEL", True), \
         patch("src.receita.async_playwright", return_value=mock_pw):
        resultado = await executar_receita(receita, {"usuario": "admin"})

    assert resultado.sucesso is True
    assert resultado.passos_executados == 2
    assert resultado.saida_capturada == "CONF-9999"


@pytest.mark.asyncio
async def test_executar_receita_variaveis_faltando():
    from src.receita import executar_receita
    receita = _fazer_receita_completa()

    resultado = await executar_receita(receita, {})  # sem variáveis

    assert resultado.sucesso is False
    assert "ausentes" in resultado.erro


@pytest.mark.asyncio
async def test_executar_receita_passo_opcional_nao_quebra():
    from src.receita import executar_receita
    receita = Receita(
        id="demo",
        nome="Demo",
        descricao="Demo",
        url="https://demo.com",
        credenciais_chave=[],
        passos=[
            PassoReceita(tipo="click", seletor=".nao_existe", opcional=True),
            PassoReceita(tipo="click", seletor="button#ok"),
        ],
        delay_humano_ms=0,
    )
    mock_pw = _montar_mock_playwright()
    locator_mock = mock_pw.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value.locator.return_value
    # Primeiro click falha, segundo ok
    locator_mock.click = AsyncMock(side_effect=[Exception("not found"), None])

    with patch("src.receita.PLAYWRIGHT_DISPONIVEL", True), \
         patch("src.receita.async_playwright", return_value=mock_pw):
        resultado = await executar_receita(receita, {})

    assert resultado.sucesso is True


@pytest.mark.asyncio
async def test_executar_receita_passo_obrigatorio_falha():
    from src.receita import executar_receita
    receita = Receita(
        id="demo",
        nome="Demo",
        descricao="Demo",
        url="https://demo.com",
        credenciais_chave=[],
        passos=[
            PassoReceita(tipo="click", seletor=".inexistente", opcional=False),
        ],
        delay_humano_ms=0,
    )
    mock_pw = _montar_mock_playwright()
    locator_mock = mock_pw.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value.locator.return_value
    locator_mock.click = AsyncMock(side_effect=Exception("element not found"))

    with patch("src.receita.PLAYWRIGHT_DISPONIVEL", True), \
         patch("src.receita.async_playwright", return_value=mock_pw):
        resultado = await executar_receita(receita, {})

    assert resultado.sucesso is False
    assert resultado.erro != ""


# ── Receita real do QuickBooks (só carregamento e validação) ──────────────────

def test_carregar_receita_quickbooks():
    receita = carregar_receita("lancamento_quickbooks")
    assert receita.id == "lancamento_quickbooks"
    assert len(receita.passos) > 5
    assert "qb_email" in receita.credenciais_chave
    assert "valor" in receita.credenciais_chave


def test_validar_variaveis_quickbooks_faltando():
    receita = carregar_receita("lancamento_quickbooks")
    faltando = validar_variaveis(receita, {"qb_email": "x@x.com"})
    assert "qb_senha" in faltando
    assert "valor" in faltando

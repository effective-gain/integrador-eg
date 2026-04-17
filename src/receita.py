"""
Engine de Receitas — executa automações em portais externos via Playwright.
Formato: GATILHO + URL + CREDENCIAIS + PASSO A PASSO + SAÍDA

Cada receita é um arquivo YAML. O engine carrega, valida e executa.
Todo resultado (sucesso ou erro) é registrado no diário do Obsidian.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_DISPONIVEL = True
except ImportError:
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_DISPONIVEL = False

logger = logging.getLogger(__name__)

RECEITAS_DIR = Path(__file__).parent.parent / "receitas"


# ── Modelos de Receita ────────────────────────────────────────────────────────

@dataclass
class PassoReceita:
    tipo: str           # click | fill | wait | screenshot | select | check_text
    seletor: str = ""
    valor: str = ""     # pode conter {variavel} para substituição em runtime
    descricao: str = ""
    opcional: bool = False
    timeout_ms: int = 10000


@dataclass
class Receita:
    id: str
    nome: str
    descricao: str
    url: str
    credenciais_chave: list[str]    # nomes das variáveis de credencial necessárias
    passos: list[PassoReceita]
    saida_seletor: str = ""         # seletor para capturar confirmação final
    saida_descricao: str = ""
    delay_humano_ms: int = 800      # delay entre ações (simula humano)


class ReceitaError(Exception):
    pass


class ReceitaValidacaoError(ReceitaError):
    pass


# ── Carregamento e Validação ──────────────────────────────────────────────────

def _substituir_variaveis(texto: str, variaveis: dict[str, str]) -> str:
    """Substitui {chave} no texto pelos valores do dict."""
    for chave, valor in variaveis.items():
        texto = texto.replace(f"{{{chave}}}", valor)
    # Verifica se sobrou alguma variável não substituída
    pendentes = re.findall(r"\{(\w+)\}", texto)
    if pendentes:
        raise ReceitaValidacaoError(f"Variáveis não fornecidas: {pendentes}")
    return texto


def carregar_receita(receita_id: str) -> Receita:
    """Carrega receita do diretório receitas/ pelo ID."""
    caminho = RECEITAS_DIR / f"{receita_id}.yaml"
    if not caminho.exists():
        raise ReceitaError(f"Receita '{receita_id}' não encontrada em {RECEITAS_DIR}")

    with caminho.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f)

    try:
        passos = [
            PassoReceita(
                tipo=p["tipo"],
                seletor=p.get("seletor", ""),
                valor=p.get("valor", ""),
                descricao=p.get("descricao", ""),
                opcional=p.get("opcional", False),
                timeout_ms=p.get("timeout_ms", 10000),
            )
            for p in dados.get("passos", [])
        ]
        return Receita(
            id=dados["id"],
            nome=dados["nome"],
            descricao=dados["descricao"],
            url=dados["url"],
            credenciais_chave=dados.get("credenciais_chave", []),
            passos=passos,
            saida_seletor=dados.get("saida_seletor", ""),
            saida_descricao=dados.get("saida_descricao", ""),
            delay_humano_ms=dados.get("delay_humano_ms", 800),
        )
    except KeyError as e:
        raise ReceitaValidacaoError(f"Campo obrigatório ausente na receita: {e}")


def validar_variaveis(receita: Receita, variaveis: dict[str, str]) -> list[str]:
    """Retorna lista de credenciais/variáveis faltantes."""
    faltando = [k for k in receita.credenciais_chave if k not in variaveis]
    return faltando


# ── Executor ──────────────────────────────────────────────────────────────────

@dataclass
class ResultadoReceita:
    receita_id: str
    sucesso: bool
    saida_capturada: str = ""
    erro: str = ""
    passos_executados: int = 0
    screenshot_path: str = ""


async def executar_receita(
    receita: Receita,
    variaveis: dict[str, str],
    headless: bool = True,
    screenshots_dir: Path | None = None,
) -> ResultadoReceita:
    """
    Executa uma receita via Playwright com delays humanos.
    Importação lazy do Playwright para não quebrar testes sem playwright instalado.
    """
    faltando = validar_variaveis(receita, variaveis)
    if faltando:
        return ResultadoReceita(
            receita_id=receita.id,
            sucesso=False,
            erro=f"Variáveis obrigatórias ausentes: {faltando}",
        )

    if not PLAYWRIGHT_DISPONIVEL or async_playwright is None:
        return ResultadoReceita(
            receita_id=receita.id,
            sucesso=False,
            erro="Playwright não instalado. Execute: pip install playwright && playwright install chromium",
        )

    resultado = ResultadoReceita(receita_id=receita.id, sucesso=False)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            url_resolvida = _substituir_variaveis(receita.url, variaveis)
            logger.info("Receita '%s': abrindo %s", receita.id, url_resolvida)
            await page.goto(url_resolvida, wait_until="networkidle")

            for i, passo in enumerate(receita.passos):
                try:
                    await _executar_passo(page, passo, variaveis, receita.delay_humano_ms)
                    resultado.passos_executados += 1
                    logger.info("Passo %d/%d OK: %s", i + 1, len(receita.passos), passo.descricao or passo.tipo)
                except Exception as e:
                    if passo.opcional:
                        logger.warning("Passo opcional falhou (ignorando): %s — %s", passo.descricao, e)
                    else:
                        raise ReceitaError(f"Passo {i+1} ({passo.descricao or passo.tipo}): {e}") from e

            # Captura saída
            if receita.saida_seletor:
                try:
                    elem = page.locator(receita.saida_seletor)
                    resultado.saida_capturada = await elem.inner_text(timeout=5000)
                except Exception:
                    resultado.saida_capturada = "(não foi possível capturar confirmação)"

            # Screenshot final
            if screenshots_dir:
                from datetime import datetime
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                nome = f"{receita.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                caminho_ss = screenshots_dir / nome
                await page.screenshot(path=str(caminho_ss), full_page=True)
                resultado.screenshot_path = str(caminho_ss)
                logger.info("Screenshot salvo: %s", caminho_ss)

            resultado.sucesso = True

        except ReceitaError as e:
            resultado.erro = str(e)
            logger.error("Receita '%s' falhou: %s", receita.id, e)
        except Exception as e:
            resultado.erro = f"Erro inesperado: {e}"
            logger.error("Receita '%s' erro inesperado: %s", receita.id, e, exc_info=True)
        finally:
            await browser.close()

    return resultado


async def _executar_passo(page, passo: PassoReceita, variaveis: dict, delay_ms: int) -> None:
    """Executa um único passo com delay humano."""
    seletor = _substituir_variaveis(passo.seletor, variaveis) if passo.seletor else ""
    valor = _substituir_variaveis(passo.valor, variaveis) if passo.valor else ""

    # Delay humano antes de cada ação (exceto waits)
    if passo.tipo not in ("wait", "screenshot"):
        await asyncio.sleep(delay_ms / 1000)

    if passo.tipo == "click":
        await page.locator(seletor).click(timeout=passo.timeout_ms)

    elif passo.tipo == "fill":
        locator = page.locator(seletor)
        await locator.clear()
        # Digita caractere a caractere com variação (mais humano)
        await locator.type(valor, delay=50)

    elif passo.tipo == "select":
        await page.locator(seletor).select_option(value=valor, timeout=passo.timeout_ms)

    elif passo.tipo == "wait":
        ms = int(valor) if valor.isdigit() else 2000
        await asyncio.sleep(ms / 1000)

    elif passo.tipo == "wait_selector":
        await page.locator(seletor).wait_for(state="visible", timeout=passo.timeout_ms)

    elif passo.tipo == "screenshot":
        # Screenshot intermediário para debug
        logger.debug("Screenshot intermediário no passo: %s", passo.descricao)

    elif passo.tipo == "check_text":
        # Valida que o texto existe na página
        conteudo = await page.content()
        if valor not in conteudo:
            raise ReceitaError(f"Texto esperado não encontrado: '{valor}'")

    else:
        raise ReceitaError(f"Tipo de passo desconhecido: '{passo.tipo}'")

"""
instagram_keeper.py
-------------------
Verifica se a sessão do Instagram está ativa.
Se expirada, reabre o Chrome com perfil salvo e refaz o login
usando as credenciais já salvas no gerenciador de senhas do Chrome.

Uso:
    python instagram_keeper.py              # verifica uma vez
    python instagram_keeper.py --loop 30   # loop a cada 30 minutos
    python instagram_keeper.py --status    # só checa, não faz login

Chamado pelo n8n workflow INSTA_KEEPER via Schedule + Execute Command.
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ─── Configuração ────────────────────────────────────────────────────────────

CHROME_PROFILE_PATH = Path.home() / "AppData/Local/Google/Chrome/User Data"
INSTAGRAM_URL       = "https://www.instagram.com/"
LOGIN_CHECK_URL     = "https://www.instagram.com/accounts/edit/"   # redireciona para login se sessão morta
HEADLESS            = False   # False = abre Chrome visível para evitar detecção
LOG_FILE            = Path(__file__).parent / "instagram_keeper.log"

# ─── Utilitários ─────────────────────────────────────────────────────────────

def log(msg: str):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def ensure_playwright():
    """Instala playwright se ainda não estiver instalado."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        log("Playwright não encontrado. Instalando...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        log("Playwright instalado com sucesso.")

# ─── Lógica principal ─────────────────────────────────────────────────────────

def check_session() -> bool:
    """
    Abre Chrome com perfil existente, navega para /accounts/edit/
    e verifica se está logado ou foi redirecionado para o login.
    Retorna True se logado, False se sessão expirada.
    """
    ensure_playwright()
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    log("Verificando sessão Instagram...")

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(CHROME_PROFILE_PATH),
                channel="chrome",
                headless=HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                ignore_https_errors=True,
                slow_mo=300,
            )

            page = ctx.new_page()
            page.goto(LOGIN_CHECK_URL, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2_000)

            current_url = page.url
            is_logged_in = "accounts/edit" in current_url or (
                "login" not in current_url and "accounts" not in current_url.split("instagram.com/")[1][:15]
                if "instagram.com/" in current_url else False
            )

            # Checagem extra: procura elemento exclusivo do feed logado
            if not is_logged_in:
                try:
                    page.wait_for_selector('input[name="username"]', timeout=4_000)
                    is_logged_in = False
                except PWTimeout:
                    is_logged_in = True

            ctx.close()
            return is_logged_in

        except Exception as e:
            log(f"Erro ao verificar sessão: {e}")
            return False


def restore_session() -> bool:
    """
    Abre Chrome com perfil existente, navega para o login do Instagram
    e usa as credenciais salvas no Chrome para reautenticar.
    NÃO armazena nem manipula a senha — usa o autofill nativo do Chrome.
    Retorna True se login bem-sucedido.
    """
    ensure_playwright()
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    log("Sessão expirada. Iniciando restauração de login...")

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(CHROME_PROFILE_PATH),
                channel="chrome",
                headless=False,      # Instagram bloqueia headless; mantém visível
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                ],
                ignore_https_errors=True,
                slow_mo=400,
            )

            page = ctx.new_page()
            page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2_000)

            # Se já está logado após navegar para home, ótimo
            if "login" not in page.url:
                log("✅ Sessão já restaurada após navegação para home.")
                ctx.close()
                return True

            # Encontra campo de usuário e aciona o autofill do Chrome
            try:
                username_field = page.locator('input[name="username"]')
                username_field.wait_for(state="visible", timeout=8_000)
                username_field.click()
                page.wait_for_timeout(500)

                # Ctrl+A seleciona tudo → Chrome mostra opção de autofill
                page.keyboard.press("Control+a")
                page.wait_for_timeout(800)

                # Seta para baixo navega no dropdown de autofill do Chrome
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1_500)

                # Submete o formulário
                submit_btn = page.locator('button[type="submit"]')
                if submit_btn.is_visible():
                    submit_btn.click()
                else:
                    page.keyboard.press("Enter")

                # Aguarda redirecionamento pós-login
                page.wait_for_timeout(5_000)

                if "login" not in page.url:
                    log(f"✅ Login restaurado com sucesso. URL: {page.url}")
                    ctx.close()
                    return True
                else:
                    log(f"❌ Autofill não funcionou. URL atual: {page.url}")
                    log("   → Abra o Chrome manualmente e confirme que a senha está salva.")
                    ctx.close()
                    return False

            except PWTimeout:
                log("❌ Campo de login não encontrado dentro do timeout.")
                ctx.close()
                return False

        except Exception as e:
            log(f"Erro ao restaurar sessão: {e}")
            return False


def run_once(status_only=False):
    """Executa uma verificação/restauração única."""
    logged_in = check_session()

    if logged_in:
        log("✅ Instagram: sessão ativa.")
        return True

    if status_only:
        log("⚠️  Instagram: sessão expirada (modo status, sem restauração).")
        return False

    success = restore_session()
    if not success:
        log("🔴 Falha ao restaurar sessão. Intervenção manual necessária.")
    return success


def run_loop(interval_minutes: int):
    """Loop contínuo de verificação."""
    log(f"🔁 Loop iniciado — verificação a cada {interval_minutes} minutos.")
    while True:
        run_once()
        log(f"   Próxima verificação em {interval_minutes} min.")
        time.sleep(interval_minutes * 60)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Session Keeper")
    parser.add_argument("--loop", type=int, metavar="MINUTOS",
                        help="Executa em loop com intervalo em minutos")
    parser.add_argument("--status", action="store_true",
                        help="Só verifica status, não restaura")
    args = parser.parse_args()

    if args.loop:
        run_loop(args.loop)
    else:
        ok = run_once(status_only=args.status)
        sys.exit(0 if ok else 1)

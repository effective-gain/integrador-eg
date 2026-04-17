"""
test_obsidian.py — Testa conexão com Obsidian REST API
Lê credenciais do .env — nunca hardcoded.

Uso:
  python scripts/test_obsidian.py

Requer:
  - .env com OBSIDIAN_API_KEY e OBSIDIAN_API_URL
  - Obsidian aberto com plugin REST API ativo
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

import requests

API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
BASE_URL = os.environ.get("OBSIDIAN_API_URL", "http://localhost:27124")
# Para HTTPS com cert auto-assinado: defina OBSIDIAN_CERT=/caminho/obsidian.pem no .env
CERT = os.environ.get("OBSIDIAN_CERT", False)

if not API_KEY:
    print("❌ OBSIDIAN_API_KEY não configurada no .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def test_status():
    print("1. Testando status da API...")
    r = requests.get(f"{BASE_URL}/", verify=CERT)
    data = r.json()
    print(f"   Status: {data.get('status')}")
    print(f"   Versão: {data.get('versions', {}).get('self')}")
    return data.get("status") == "OK"


def test_read_home():
    print("2. Lendo HOME.md...")
    r = requests.get(f"{BASE_URL}/vault/HOME.md", headers=HEADERS, verify=CERT)
    if r.status_code == 200:
        print(f"   HOME.md lido ({len(r.text)} chars)")
        return True
    print(f"   Erro: {r.status_code}")
    return False


def test_create_note():
    print("3. Criando nota de teste...")
    payload = "---\ntipo: teste\n---\n\n# Teste WhatsApp OS\n\nNota criada pelo test_obsidian.py"
    r = requests.put(
        f"{BASE_URL}/vault/04%20-%20Inbox/teste-whatsapp-os.md",
        headers={**HEADERS, "Content-Type": "text/markdown"},
        data=payload.encode("utf-8"),
        verify=CERT,
    )
    if r.status_code in [200, 204]:
        print("   Nota criada em 04 - Inbox/")
        return True
    print(f"   Erro: {r.status_code} — {r.text}")
    return False


def test_list_projects():
    print("4. Listando projetos ativos...")
    r = requests.get(f"{BASE_URL}/vault/01%20-%20Projetos/", headers=HEADERS, verify=CERT)
    if r.status_code == 200:
        files = r.json().get("files", [])
        print(f"   {len(files)} arquivos em 01 - Projetos/")
        for f in files[:5]:
            print(f"   - {f}")
        return True
    print(f"   Erro: {r.status_code}")
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("WhatsApp OS — Teste Obsidian REST API")
    print("=" * 50)
    results = [test_status(), test_read_home(), test_create_note(), test_list_projects()]
    passed = sum(results)
    print("=" * 50)
    print(f"Resultado: {passed}/{len(results)} testes passaram")
    print("✅ Pronta para integração" if passed == len(results) else "❌ Corrija os erros antes de configurar o n8n")

"""
test_obsidian.py — Testa conexão com Obsidian REST API
Roda antes de configurar o n8n para garantir que o vault está acessível.
"""

import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_KEY = "de3cef3d55131b7d2eb38033ee9878fdedd84e320d803b99517b600079bc5edd"
BASE_URL = "https://127.0.0.1:27124"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def test_status():
    print("1. Testando status da API...")
    r = requests.get(f"{BASE_URL}/", verify=False)
    data = r.json()
    print(f"   Status: {data.get('status')}")
    print(f"   Versão: {data.get('versions', {}).get('self')}")
    return data.get("status") == "OK"

def test_read_home():
    print("2. Lendo HOME.md...")
    r = requests.get(
        f"{BASE_URL}/vault/HOME.md",
        headers=HEADERS,
        verify=False
    )
    if r.status_code == 200:
        print(f"   HOME.md lido com sucesso ({len(r.text)} chars)")
        return True
    else:
        print(f"   Erro: {r.status_code}")
        return False

def test_create_note():
    print("3. Criando nota de teste...")
    payload = "---\ntipo: teste\n---\n\n# Teste WhatsApp OS\n\nNota criada pelo test_obsidian.py"
    r = requests.put(
        f"{BASE_URL}/vault/04%20-%20Inbox/teste-whatsapp-os.md",
        headers={**HEADERS, "Content-Type": "text/markdown"},
        data=payload.encode("utf-8"),
        verify=False
    )
    if r.status_code in [200, 204]:
        print("   Nota criada com sucesso em 04 - Inbox/")
        return True
    else:
        print(f"   Erro: {r.status_code} — {r.text}")
        return False

def test_list_projects():
    print("4. Listando projetos ativos...")
    r = requests.get(
        f"{BASE_URL}/vault/01%20-%20Projetos/",
        headers=HEADERS,
        verify=False
    )
    if r.status_code == 200:
        files = r.json().get("files", [])
        print(f"   {len(files)} arquivos em 01 - Projetos/")
        for f in files[:5]:
            print(f"   - {f}")
        return True
    else:
        print(f"   Erro: {r.status_code}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("WhatsApp OS — Teste Obsidian REST API")
    print("=" * 50)

    results = [
        test_status(),
        test_read_home(),
        test_create_note(),
        test_list_projects()
    ]

    passed = sum(results)
    print("=" * 50)
    print(f"Resultado: {passed}/{len(results)} testes passaram")
    if passed == len(results):
        print("✅ Obsidian REST API pronta para integração com n8n")
    else:
        print("❌ Corrija os erros antes de configurar o n8n")

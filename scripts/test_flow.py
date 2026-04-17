"""
test_flow.py — Simula o fluxo completo sem WhatsApp
Testa: mensagem → classificador → Obsidian → resposta
Usar antes de ativar nos grupos reais.
"""

import anthropic
import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Config Obsidian
OBSIDIAN_KEY = "de3cef3d55131b7d2eb38033ee9878fdedd84e320d803b99517b600079bc5edd"
OBSIDIAN_URL = "https://127.0.0.1:27124"
OBSIDIAN_HEADERS = {
    "Authorization": f"Bearer {OBSIDIAN_KEY}",
    "Content-Type": "text/markdown"
}

# Config Claude
client = anthropic.Anthropic()
CLASSIFIER_PROMPT = open("../prompts/classifier.md").read()
RESPONDER_PROMPT = open("../prompts/responder.md").read()

GRUPOS_PROJETOS = {
    "k2con": "01 - Projetos/K2Con.md",
    "eg_food": "01 - Projetos/EG Food.md",
    "gestao_eg": "01 - Projetos/Gestao EG.md",
    "mkt_eg": "01 - Projetos/MKT EG.md",
    "quickbooks": "01 - Projetos/Quickbooks WhatsApp.md",
    "geral": "04 - Inbox/"
}

def step1_classificar(grupo: str, mensagem: str) -> dict:
    """Classifica a intenção da mensagem via Claude"""
    prompt = f"{CLASSIFIER_PROMPT}\n\nGrupo: {grupo}\nMensagem: {mensagem}"
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    texto = response.content[0].text.strip()
    inicio = texto.find("{")
    fim = texto.rfind("}") + 1
    return json.loads(texto[inicio:fim])

def step2_executar_obsidian(acao: dict, grupo: str) -> bool:
    """Executa a ação no Obsidian via REST API"""
    from datetime import datetime
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    hora_agora = datetime.now().strftime("%H:%M")

    if acao["acao"] == "criar_nota":
        caminho = f"04 - Inbox/{data_hoje}-{grupo}.md"
        conteudo = f"---\ntipo: inbox\ndata: {data_hoje}\ntags: [inbox, {grupo}]\n---\n\n# {acao['conteudo'][:50]}\n\n{acao['conteudo']}\n"

    elif acao["acao"] == "criar_reuniao":
        caminho = f"04 - Inbox/Reuniao-{data_hoje}-{grupo}.md"
        conteudo = f"---\ntipo: reuniao\ndata: {data_hoje}\nprojeto: {acao['projeto']}\ntags: [reuniao, {grupo}]\n---\n\n# Reuniao {data_hoje}\n\n## Discussao\n{acao['conteudo']}\n\n## Acoes\n- [ ] \n"

    elif acao["acao"] == "criar_task":
        caminho = acao.get("destinatario", f"04 - Inbox/{data_hoje}-task.md")
        conteudo = f"\n- [ ] {acao['conteudo']} — {data_hoje}\n"
        # Para tasks, faz append na nota do projeto
        r = requests.post(
            f"{OBSIDIAN_URL}/vault/{caminho.replace(' ', '%20')}",
            headers=OBSIDIAN_HEADERS,
            data=conteudo.encode("utf-8"),
            verify=False
        )
        return r.status_code in [200, 204]

    elif acao["acao"] == "registrar_lancamento":
        caminho = f"04 - Inbox/Lancamento-{data_hoje}-{grupo}.md"
        conteudo = f"---\ntipo: lancamento\ndata: {data_hoje}\nprojeto: {acao['projeto']}\ntags: [financeiro, {grupo}]\n---\n\n# Lancamento {data_hoje}\n\n{acao['conteudo']}\n"

    else:
        caminho = f"04 - Inbox/{data_hoje}-{acao['acao']}-{grupo}.md"
        conteudo = f"---\ntipo: {acao['acao']}\ndata: {data_hoje}\ntags: [{grupo}]\n---\n\n{acao['conteudo']}\n"

    r = requests.put(
        f"{OBSIDIAN_URL}/vault/{caminho.replace(' ', '%20')}",
        headers=OBSIDIAN_HEADERS,
        data=conteudo.encode("utf-8"),
        verify=False
    )
    return r.status_code in [200, 204]

def step3_gerar_resposta(acao: dict) -> str:
    """Gera resposta para enviar no WhatsApp"""
    prompt = f"{RESPONDER_PROMPT}\n\nAção: {acao['acao']}\nProjeto: {acao['projeto']}\nConteúdo: {acao['conteudo']}\nDestinatário: {acao.get('destinatario', '04 - Inbox/')}"
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

def simular_mensagem(grupo: str, mensagem: str):
    print(f"\n{'='*50}")
    print(f"SIMULANDO — Grupo: {grupo}")
    print(f"Mensagem: {mensagem}")
    print("-" * 50)

    print("→ Step 1: Classificando intenção...")
    acao = step1_classificar(grupo, mensagem)
    print(f"  Ação: {acao['acao']} | Projeto: {acao['projeto']} | Prioridade: {acao['prioridade']}")

    print("→ Step 2: Executando no Obsidian...")
    ok = step2_executar_obsidian(acao, grupo)
    print(f"  Resultado: {'✅ Sucesso' if ok else '❌ Falhou'}")

    print("→ Step 3: Gerando resposta WhatsApp...")
    resposta = step3_gerar_resposta(acao)
    print(f"  Resposta:\n  {resposta}")

if __name__ == "__main__":
    print("WhatsApp OS — Teste de Fluxo Completo")

    # Mensagens de teste
    simular_mensagem("k2con", "Reunião com cliente hoje, pediram ajuste na proposta")
    simular_mensagem("gestao_eg", "Allp Fit pagou abril, lança no financeiro")
    simular_mensagem("mkt_eg", "Criar post LinkedIn sobre AI First para semana que vem")

    print(f"\n{'='*50}")
    print("Fluxo testado. Verifique 04 - Inbox/ no Obsidian.")

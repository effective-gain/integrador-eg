"""
test_classifier.py — Testa o classificador de intenção Claude
Simula mensagens de cada grupo e valida o JSON retornado.
"""

import anthropic
import json

client = anthropic.Anthropic()

CLASSIFIER_PROMPT = open("../prompts/classifier.md").read()

GRUPOS_PROJETOS = {
    "k2con": "01 - Projetos/K2Con.md",
    "eg_food": "01 - Projetos/EG Food.md",
    "gestao_eg": "01 - Projetos/Gestao EG.md",
    "mkt_eg": "01 - Projetos/MKT EG.md",
    "quickbooks": "01 - Projetos/Quickbooks WhatsApp.md",
    "geral": "04 - Inbox/"
}

TESTES = [
    {
        "grupo": "k2con",
        "mensagem": "Tivemos reunião hoje, cliente pediu ajustar proposta para incluir SDR",
        "acao_esperada": "criar_reuniao"
    },
    {
        "grupo": "gestao_eg",
        "mensagem": "Allp Fit pagou a parcela de abril, lança no fluxo de caixa",
        "acao_esperada": "registrar_lancamento"
    },
    {
        "grupo": "mkt_eg",
        "mensagem": "Preciso criar um post para o LinkedIn sobre AI First",
        "acao_esperada": "criar_task"
    },
    {
        "grupo": "eg_food",
        "mensagem": "Reunião com Beef Smash amanhã às 14h para revisar automações",
        "acao_esperada": "criar_reuniao"
    },
    {
        "grupo": "geral",
        "mensagem": "Ideia: criar um dashboard unificado para todos os clientes",
        "acao_esperada": "criar_nota"
    }
]

def classificar(grupo: str, mensagem: str) -> dict:
    prompt = f"{CLASSIFIER_PROMPT}\n\nGrupo: {grupo}\nMensagem: {mensagem}"
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    texto = response.content[0].text.strip()
    # Extrai JSON do texto
    inicio = texto.find("{")
    fim = texto.rfind("}") + 1
    return json.loads(texto[inicio:fim])

if __name__ == "__main__":
    print("=" * 50)
    print("WhatsApp OS — Teste Classificador Claude")
    print("=" * 50)

    passou = 0
    for i, teste in enumerate(TESTES, 1):
        print(f"\nTeste {i} — Grupo: {teste['grupo']}")
        print(f"Mensagem: {teste['mensagem'][:60]}...")
        try:
            resultado = classificar(teste["grupo"], teste["mensagem"])
            print(f"Resultado: {json.dumps(resultado, ensure_ascii=False, indent=2)}")
            if resultado.get("acao") == teste["acao_esperada"]:
                print(f"✅ Ação correta: {resultado['acao']}")
                passou += 1
            else:
                print(f"⚠️  Esperado: {teste['acao_esperada']} | Recebido: {resultado.get('acao')}")
        except Exception as e:
            print(f"❌ Erro: {e}")

    print("\n" + "=" * 50)
    print(f"Resultado: {passou}/{len(TESTES)} testes passaram")
    if passou == len(TESTES):
        print("✅ Classificador pronto para integração com n8n")
    else:
        print("⚠️  Ajuste o prompt em prompts/classifier.md e teste novamente")

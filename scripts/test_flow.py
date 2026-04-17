"""
test_flow.py — Teste de fluxo completo do Integrador EG
Testa: classificação Claude + escrita Obsidian + diário

Uso:
  python scripts/test_flow.py

Requer:
  - .env com ANTHROPIC_API_KEY e OBSIDIAN_API_KEY
  - Obsidian aberto com plugin REST API ativo na porta 27124
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.classifier import Classifier
from src.models import AcaoTipo, DiarioEntrada, MensagemEntrada
from src.obsidian import ObsidianClient, ObsidianError

VERDE = "\033[92m"
VERMELHO = "\033[91m"
AMARELO = "\033[93m"
RESET = "\033[0m"
NEGRITO = "\033[1m"

CASOS = [
    {"descricao": "Nota simples PT",       "grupo": "gestao-eg", "mensagem": "preciso registrar que o fornecedor confirmou entrega para sexta",     "acao_esperada": AcaoTipo.CRIAR_NOTA},
    {"descricao": "Task com prazo",         "grupo": "k2con",     "mensagem": "criar task: revisar proposta comercial até quinta-feira",            "acao_esperada": AcaoTipo.CRIAR_TASK},
    {"descricao": "Lançamento financeiro",  "grupo": "gestao-eg", "mensagem": "lançamento: pagamento Cliff $500 referente novembro",               "acao_esperada": AcaoTipo.REGISTRAR_LANCAMENTO},
    {"descricao": "Mensagem ambígua",       "grupo": "gestao-eg", "mensagem": "reunião",                                                           "acao_esperada": AcaoTipo.AMBIGUA},
    {"descricao": "Consulta de pendências", "grupo": "k2con",     "mensagem": "o que está pendente no projeto?",                                   "acao_esperada": AcaoTipo.CONSULTAR_TASKS},
    {"descricao": "Mensagem em espanhol",   "grupo": "eg-build",  "mensagem": "necesito registrar una decisión: cambiamos el proveedor",           "acao_esperada": AcaoTipo.REGISTRAR_DECISAO},
]


def ok(msg):    print(f"  {VERDE}✅ {msg}{RESET}")
def erro(msg):  print(f"  {VERMELHO}❌ {msg}{RESET}")
def aviso(msg): print(f"  {AMARELO}⚠️  {msg}{RESET}")
def h(msg):     print(f"\n{NEGRITO}{msg}{RESET}")


async def checar_obsidian(client):
    h("[ 1 ] Conexão Obsidian")
    ok_obs = await client.health_check()
    ok("Obsidian respondendo") if ok_obs else erro("Obsidian offline — abra com plugin REST API ativo")
    return ok_obs


async def checar_diario(client):
    h("[ 2 ] Escrita no diário")
    try:
        await client.registrar_diario(DiarioEntrada(
            grupo="gestao-eg", projeto="Gestão EG",
            acao=AcaoTipo.CRIAR_NOTA,
            conteudo_resumo="[teste automático] validação pipeline",
            resultado="sucesso",
        ))
        ok("Diário atualizado no Obsidian")
        return True
    except ObsidianError as e:
        erro(f"Falha ao escrever no diário: {e}")
        return False


def checar_classificador(clf):
    h("[ 3 ] Classificador Claude")
    acertos = 0
    for caso in CASOS:
        msg = MensagemEntrada(
            grupo_id=f"{caso['grupo']}@g.us", grupo_nome=caso["grupo"],
            remetente="Teste", conteudo=caso["mensagem"], timestamp=datetime.now(),
        )
        try:
            r = clf.classificar(msg)
            if r.acao == caso["acao_esperada"]:
                ok(f"{caso['descricao']} → {r.acao.value}  |  \"{r.resumo_confirmacao}\"")
                acertos += 1
            else:
                erro(f"{caso['descricao']}\n     esperado={caso['acao_esperada'].value}  recebido={r.acao.value}")
        except Exception as e:
            erro(f"{caso['descricao']} → exceção: {e}")
    print(f"\n  {acertos}/{len(CASOS)} casos corretos")
    return acertos


async def main():
    print(f"\n{NEGRITO}{'='*55}\n  INTEGRADOR EG — PASSO 1: FLUXO COMPLETO\n{'='*55}{RESET}")

    api_key     = os.getenv("ANTHROPIC_API_KEY")
    obs_key     = os.getenv("OBSIDIAN_API_KEY", "")
    obs_url     = os.getenv("OBSIDIAN_API_URL", "http://localhost:27124")

    if not api_key:
        erro("ANTHROPIC_API_KEY não configurada no .env"); sys.exit(1)

    obsidian = ObsidianClient(base_url=obs_url, api_key=obs_key)
    clf      = Classifier(api_key=api_key)

    obs_ok    = await checar_obsidian(obsidian)
    diario_ok = await checar_diario(obsidian) if obs_ok else False
    acertos   = checar_classificador(clf)

    h("[ RESUMO ]")
    print(f"  Obsidian:      {'✅' if obs_ok else '❌'}")
    print(f"  Diário:        {'✅' if diario_ok else '❌'}")
    print(f"  Classificador: {acertos}/{len(CASOS)}")

    tudo_ok = obs_ok and diario_ok and acertos == len(CASOS)
    if tudo_ok:
        print(f"\n{VERDE}{NEGRITO}  PASSO 1 APROVADO ✅{RESET}\n")
    else:
        print(f"\n{AMARELO}{NEGRITO}  PASSO 1 INCOMPLETO — ajuste os itens acima{RESET}\n")
    sys.exit(0 if tudo_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())

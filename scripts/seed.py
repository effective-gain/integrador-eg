"""
Seed inicial do banco de dados.
Cria o admin EG e os clientes mapeados nos grupos WhatsApp.

Uso:
    python scripts/seed.py
    python scripts/seed.py --reset   # apaga execucoes/clientes antes de reinserir
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import bcrypt
from dotenv import load_dotenv

load_dotenv()

from src.config import settings  # noqa: E402

# ── clientes iniciais (espelham GRUPOS_PROJETOS em models.py) ──────────────
CLIENTES = [
    {"nome": "K2Con",            "slug": "k2con",       "whatsapp_grupo": "k2con",     "plano": "premium"},
    {"nome": "Beef Smash & Co",  "slug": "beef-smash",  "whatsapp_grupo": "beef-smash","plano": "premium"},
    {"nome": "RODAG",            "slug": "rodag",       "whatsapp_grupo": "rodag",     "plano": "premium"},
    {"nome": "Gestão EG",        "slug": "gestao-eg",   "whatsapp_grupo": "gestao-eg", "plano": "premium"},
    {"nome": "EG Build",         "slug": "eg-build",    "whatsapp_grupo": "eg-build",  "plano": "premium"},
    {"nome": "MKT EG",           "slug": "mkt-eg",      "whatsapp_grupo": "mkt-eg",    "plano": "basic"},
]

# ── receitas de exemplo por cliente ───────────────────────────────────────
RECEITAS_EXEMPLO = [
    {"cliente_slug": "k2con",   "nome": "Criar nota de reunião",      "gatilho": "Mensagem com pauta ou ata",   "sistema_destino": "Obsidian", "descricao": "Registra reuniões e pautas no vault do projeto K2Con."},
    {"cliente_slug": "k2con",   "nome": "Registrar decisão",          "gatilho": "Mensagem com 'decidimos'",    "sistema_destino": "Obsidian", "descricao": "Documenta decisões estratégicas com data e responsável."},
    {"cliente_slug": "rodag",   "nome": "Lançamento QuickBooks",      "gatilho": "Invoice ou cupom no grupo",   "sistema_destino": "QuickBooks", "descricao": "Faz login no QuickBooks e lança o documento financeiro automaticamente."},
    {"cliente_slug": "rodag",   "nome": "Criar task de follow-up",    "gatilho": "Mensagem com 'lembrar' ou 'follow'", "sistema_destino": "Obsidian", "descricao": "Cria task com prazo no vault do projeto."},
    {"cliente_slug": "gestao-eg", "nome": "Daily EG",                 "gatilho": "Mensagem de início de dia",  "sistema_destino": "Obsidian", "descricao": "Abre o diário do dia com agenda e pendências."},
    {"cliente_slug": "mkt-eg",  "nome": "Atualizar status campanha",  "gatilho": "Mensagem sobre campanha ativa", "sistema_destino": "Obsidian", "descricao": "Atualiza o status da campanha no arquivo do projeto MKT EG."},
]


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


async def run(reset: bool = False) -> None:
    if not settings.database_url:
        print("❌  DATABASE_URL não configurado no .env")
        sys.exit(1)

    conn = await asyncpg.connect(dsn=settings.database_url)
    print("✅  Conectado ao banco de dados")

    try:
        if reset:
            print("⚠️   --reset: removendo dados existentes...")
            await conn.execute("DELETE FROM receitas_ativas")
            await conn.execute("DELETE FROM execucoes")
            await conn.execute("DELETE FROM briefings_enviados")
            await conn.execute("DELETE FROM clientes")
            await conn.execute("DELETE FROM usuarios WHERE papel != 'admin'")
            print("   Dados removidos.")

        # ── inserir clientes ────────────────────────────────────────────
        print("\n📦  Inserindo clientes...")
        cliente_ids: dict[str, int] = {}
        for c in CLIENTES:
            row = await conn.fetchrow(
                """
                INSERT INTO clientes (nome, slug, whatsapp_grupo, plano)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (slug) DO UPDATE
                    SET nome = EXCLUDED.nome,
                        whatsapp_grupo = EXCLUDED.whatsapp_grupo,
                        plano = EXCLUDED.plano
                RETURNING id
                """,
                c["nome"], c["slug"], c["whatsapp_grupo"], c["plano"],
            )
            cliente_ids[c["slug"]] = row["id"]
            print(f"   ✔  {c['nome']} (id={row['id']})")

        # ── inserir receitas de exemplo ────────────────────────────────
        print("\n🔧  Inserindo receitas de exemplo...")
        for r in RECEITAS_EXEMPLO:
            cid = cliente_ids.get(r["cliente_slug"])
            if not cid:
                continue
            await conn.execute(
                """
                INSERT INTO receitas_ativas (cliente_id, nome, descricao, gatilho, sistema_destino, status)
                VALUES ($1, $2, $3, $4, $5, 'ativa')
                ON CONFLICT DO NOTHING
                """,
                cid, r["nome"], r["descricao"], r["gatilho"], r["sistema_destino"],
            )
            print(f"   ✔  {r['nome']} → {r['cliente_slug']}")

        # ── criar admin EG ─────────────────────────────────────────────
        print("\n👤  Criando usuário admin EG...")
        admin_email = "info@effectivegain.com"
        admin_senha = "EG@admin2026"

        existing = await conn.fetchrow("SELECT id FROM usuarios WHERE email = $1", admin_email)
        if existing:
            # garante papel admin
            await conn.execute(
                "UPDATE usuarios SET papel = 'admin', cliente_id = NULL WHERE email = $1",
                admin_email,
            )
            print(f"   ℹ️   Admin já existe (id={existing['id']}) — papel atualizado para admin.")
        else:
            row = await conn.fetchrow(
                """
                INSERT INTO usuarios (email, nome, senha_hash, papel)
                VALUES ($1, $2, $3, 'admin')
                RETURNING id
                """,
                admin_email,
                "Luiz Alberto — EG",
                hash_senha(admin_senha),
            )
            print(f"   ✔  Admin criado (id={row['id']})")
            print(f"      Email: {admin_email}")
            print(f"      Senha: {admin_senha}  ← altere após o primeiro login!")

        print("\n✅  Seed concluído com sucesso!")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed do banco Integrador EG")
    parser.add_argument("--reset", action="store_true", help="Apaga dados existentes antes de inserir")
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))

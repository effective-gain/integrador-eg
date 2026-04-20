"""Cria a tabela `usuarios` e semeia o admin padrão.

Uso:
    python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth import hash_senha
from src.db import close_pool, get_pool

ADMIN_EMAIL = "effectivegain@gmail.com"
ADMIN_SENHA = "Fiona2025@"
ADMIN_NOME = "Effective Gain"

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    nome        TEXT NOT NULL,
    senha_hash  TEXT NOT NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
        existente = await conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1", ADMIN_EMAIL.lower()
        )
        if existente:
            print(f"Usuário já existe (id={existente}): {ADMIN_EMAIL}")
            return
        await conn.execute(
            "INSERT INTO usuarios (email, nome, senha_hash) VALUES ($1, $2, $3)",
            ADMIN_EMAIL.lower(),
            ADMIN_NOME,
            hash_senha(ADMIN_SENHA),
        )
        print(f"Admin criado: {ADMIN_EMAIL}")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

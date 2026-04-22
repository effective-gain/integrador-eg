"""
Configurações dinâmicas salvas no PostgreSQL.
Permite alterar credenciais e settings via portal admin sem editar .env ou reiniciar servidor.

Hierarquia de valores:
    DB (portal) > .env > padrão do código
"""
from __future__ import annotations

import logging
from typing import Any

from .db import get_pool

logger = logging.getLogger(__name__)

# Chaves que nunca retornam valor real para o frontend — exibem "••••••••"
_CHAVES_SENSIVEIS = {
    "gmail_app_password",
    "outlook_client_secret",
    "webhook_secret",
}


async def get_config(chave: str, padrao: str = "") -> str:
    """Retorna o valor de uma configuração. Retorna `padrao` se não encontrar ou DB offline."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT valor FROM configuracoes WHERE chave = $1", chave
            )
            if row and row["valor"]:
                return row["valor"]
    except Exception as e:
        logger.warning("configuracoes.get_config('%s'): %s", chave, e)
    return padrao


async def set_config(chave: str, valor: str) -> bool:
    """Salva ou atualiza uma configuração."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO configuracoes (chave, valor, atualizado_em)
                VALUES ($1, $2, NOW())
                ON CONFLICT (chave) DO UPDATE
                    SET valor = $2, atualizado_em = NOW()
                """,
                chave,
                valor,
            )
        return True
    except Exception as e:
        logger.error("configuracoes.set_config('%s'): %s", chave, e)
        return False


async def set_many(dados: dict[str, str]) -> bool:
    """Salva múltiplas configurações em uma transação."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for chave, valor in dados.items():
                    # Ignora campos de senha que vieram mascarados (não sobrescreve)
                    if valor == "••••••••":
                        continue
                    await conn.execute(
                        """
                        INSERT INTO configuracoes (chave, valor, atualizado_em)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (chave) DO UPDATE
                            SET valor = $2, atualizado_em = NOW()
                        """,
                        chave,
                        valor,
                    )
        return True
    except Exception as e:
        logger.error("configuracoes.set_many: %s", e)
        return False


async def get_all() -> dict[str, dict[str, Any]]:
    """
    Retorna todas as configurações para exibição no portal.
    Valores sensíveis são mascarados como '••••••••'.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chave, valor, sensivel, descricao, atualizado_em
                FROM configuracoes
                ORDER BY chave
                """
            )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            valor_exibido = row["valor"] or ""
            if row["sensivel"] and valor_exibido:
                valor_exibido = "••••••••"
            result[row["chave"]] = {
                "valor": valor_exibido,
                "sensivel": row["sensivel"],
                "descricao": row["descricao"],
                "preenchido": bool(row["valor"]),
                "atualizado_em": (
                    row["atualizado_em"].isoformat() if row["atualizado_em"] else None
                ),
            }
        return result
    except Exception as e:
        logger.error("configuracoes.get_all: %s", e)
        return {}


async def carregar_para_settings() -> dict[str, str]:
    """
    Carrega todas as configurações do banco para uso no lifespan.
    Retorna dict {chave: valor} — apenas entradas com valor não-vazio.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT chave, valor FROM configuracoes WHERE valor IS NOT NULL AND valor != ''"
            )
        return {row["chave"]: row["valor"] for row in rows}
    except Exception as e:
        logger.warning("configuracoes.carregar_para_settings: %s", e)
        return {}

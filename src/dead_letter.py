"""Fila de operações Obsidian que falharam — persistida em Postgres (async)."""
from __future__ import annotations

import logging

from src.db import get_pool

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS fila_pendente (
    id                  SERIAL PRIMARY KEY,
    grupo_id            TEXT NOT NULL,
    grupo_nome          TEXT NOT NULL,
    acao                TEXT NOT NULL,
    projeto             TEXT NOT NULL,
    conteudo_formatado  TEXT NOT NULL,
    tentativas          INTEGER NOT NULL DEFAULT 0,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_erro         TEXT
);
"""


class DeadLetterQueue:
    """Fila de operações Obsidian que falharam, persistida em Postgres."""

    async def enfileirar(
        self,
        grupo_id: str,
        grupo_nome: str,
        acao: str,
        projeto: str,
        conteudo_formatado: str,
        erro: str,
    ) -> int:
        pool = await get_pool()
        item_id = await pool.fetchval(
            """INSERT INTO fila_pendente
               (grupo_id, grupo_nome, acao, projeto, conteudo_formatado, ultimo_erro)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id""",
            grupo_id, grupo_nome, acao, projeto, conteudo_formatado, erro,
        )
        logger.warning("Dead letter: enfileirado id=%d | %s → %s", item_id, acao, projeto)
        return item_id

    async def listar_pendentes(self) -> list[dict]:
        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT * FROM fila_pendente WHERE tentativas < $1 ORDER BY criado_em",
            MAX_TENTATIVAS,
        )
        return [dict(r) for r in rows]

    async def remover(self, item_id: int) -> None:
        pool = await get_pool()
        await pool.execute("DELETE FROM fila_pendente WHERE id = $1", item_id)

    async def incrementar_tentativas(self, item_id: int, erro: str) -> None:
        pool = await get_pool()
        await pool.execute(
            "UPDATE fila_pendente SET tentativas = tentativas + 1, ultimo_erro = $1 WHERE id = $2",
            erro, item_id,
        )

    async def total_pendentes(self) -> int:
        pool = await get_pool()
        return await pool.fetchval(
            "SELECT COUNT(*) FROM fila_pendente WHERE tentativas < $1",
            MAX_TENTATIVAS,
        )

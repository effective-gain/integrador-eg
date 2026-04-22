"""Camada de dados do portal — queries Postgres para o portal do cliente e painel admin."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.db import get_pool

logger = logging.getLogger(__name__)

# minutos economizados por tipo de ação (base de cálculo do ROI)
_MINUTOS_POR_ACAO: dict[str, int] = {
    "criar_nota": 10,
    "criar_reuniao": 20,
    "criar_task": 10,
    "registrar_decisao": 15,
    "registrar_lancamento": 30,
    "criar_daily": 10,
    "atualizar_status": 10,
    "consultar_tasks": 5,
}
_MINUTOS_PADRAO = 10


# ── helpers ────────────────────────────────────────────────────────────────

def _minutos_economizados(execucoes: list[dict]) -> int:
    total = 0
    for e in execucoes:
        acao = e.get("acao") or ""
        total += _MINUTOS_POR_ACAO.get(acao, _MINUTOS_PADRAO)
    return total


def _periodo_sql(periodo: str) -> str:
    """Retorna cláusula SQL para filtrar por período."""
    mapa = {
        "hoje": "NOW() - INTERVAL '1 day'",
        "semana": "NOW() - INTERVAL '7 days'",
        "mes": "NOW() - INTERVAL '30 days'",
        "tudo": "NOW() - INTERVAL '365 days'",
    }
    return mapa.get(periodo, mapa["semana"])


# ── lookup de cliente por grupo WhatsApp ───────────────────────────────────

async def buscar_cliente_por_grupo(grupo_nome: str) -> int | None:
    """Retorna o cliente_id associado ao grupo WhatsApp, ou None se não encontrado."""
    if not grupo_nome:
        return None
    pool = await get_pool()
    # 1. match exato no slug do grupo
    row = await pool.fetchrow(
        "SELECT id FROM clientes WHERE LOWER(whatsapp_grupo) = LOWER($1) AND ativo = TRUE",
        grupo_nome.strip(),
    )
    if row:
        return row["id"]
    # 2. match parcial no nome do cliente
    row = await pool.fetchrow(
        "SELECT id FROM clientes WHERE LOWER(nome) LIKE LOWER($1) AND ativo = TRUE LIMIT 1",
        f"%{grupo_nome.strip()}%",
    )
    return row["id"] if row else None


# ── portal do cliente ──────────────────────────────────────────────────────

async def get_resumo_cliente(cliente_id: int) -> dict:
    pool = await get_pool()

    execucoes_mes = await pool.fetch(
        """
        SELECT acao, resultado FROM execucoes
        WHERE cliente_id = $1
          AND resultado = 'sucesso'
          AND criado_em >= NOW() - INTERVAL '30 days'
        """,
        cliente_id,
    )
    total_mes = len(execucoes_mes)
    minutos = _minutos_economizados([dict(r) for r in execucoes_mes])
    horas = round(minutos / 60, 1)

    automacoes_ativas = await pool.fetchval(
        "SELECT COUNT(*) FROM receitas_ativas WHERE cliente_id = $1 AND status = 'ativa'",
        cliente_id,
    )
    briefings_mes = await pool.fetchval(
        """
        SELECT COUNT(*) FROM briefings_enviados
        WHERE cliente_id = $1 AND sucesso = TRUE
          AND enviado_em >= NOW() - INTERVAL '30 days'
        """,
        cliente_id,
    )
    execucoes_hoje = await pool.fetchval(
        """
        SELECT COUNT(*) FROM execucoes
        WHERE cliente_id = $1 AND resultado = 'sucesso'
          AND criado_em >= NOW() - INTERVAL '1 day'
        """,
        cliente_id,
    )

    return {
        "execucoes_mes": total_mes,
        "execucoes_hoje": execucoes_hoje or 0,
        "automacoes_ativas": automacoes_ativas or 0,
        "horas_economizadas": horas,
        "briefings_mes": briefings_mes or 0,
    }


async def get_execucoes_cliente(
    cliente_id: int,
    periodo: str = "semana",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    pool = await get_pool()
    desde = _periodo_sql(periodo)
    rows = await pool.fetch(
        f"""
        SELECT id, grupo_nome, remetente, acao, projeto, conteudo_resumo,
               resultado, erro_detalhe, criado_em
        FROM execucoes
        WHERE cliente_id = $1 AND criado_em >= {desde}
        ORDER BY criado_em DESC
        LIMIT $2 OFFSET $3
        """,
        cliente_id, limit, offset,
    )
    return [dict(r) for r in rows]


async def get_receitas_cliente(cliente_id: int) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, nome, descricao, gatilho, sistema_destino,
               status, ultima_execucao, total_execucoes, criado_em
        FROM receitas_ativas
        WHERE cliente_id = $1
        ORDER BY status, nome
        """,
        cliente_id,
    )
    return [dict(r) for r in rows]


async def get_briefings_cliente(cliente_id: int, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, data_referencia, conteudo, numero_destino, enviado_em, sucesso
        FROM briefings_enviados
        WHERE cliente_id = $1
        ORDER BY enviado_em DESC
        LIMIT $2
        """,
        cliente_id, limit,
    )
    return [dict(r) for r in rows]


# ── admin EG ───────────────────────────────────────────────────────────────

async def get_todos_clientes() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT c.id, c.nome, c.slug, c.whatsapp_grupo, c.plano, c.ativo, c.criado_em,
               COUNT(DISTINCT e.id) FILTER (WHERE e.criado_em >= NOW() - INTERVAL '30 days') AS execucoes_mes,
               COUNT(DISTINCT r.id) FILTER (WHERE r.status = 'ativa') AS receitas_ativas
        FROM clientes c
        LEFT JOIN execucoes e ON e.cliente_id = c.id
        LEFT JOIN receitas_ativas r ON r.cliente_id = c.id
        GROUP BY c.id
        ORDER BY c.nome
        """
    )
    return [dict(r) for r in rows]


async def get_resumo_global() -> dict:
    pool = await get_pool()

    total_clientes = await pool.fetchval("SELECT COUNT(*) FROM clientes WHERE ativo = TRUE")
    execucoes_hoje = await pool.fetchval(
        "SELECT COUNT(*) FROM execucoes WHERE criado_em >= NOW() - INTERVAL '1 day'"
    )
    execucoes_mes = await pool.fetchval(
        "SELECT COUNT(*) FROM execucoes WHERE criado_em >= NOW() - INTERVAL '30 days' AND resultado = 'sucesso'"
    )
    dead_letter = await pool.fetchval(
        "SELECT COUNT(*) FROM dead_letter WHERE resolvido = FALSE"
    )

    return {
        "clientes_ativos": total_clientes or 0,
        "execucoes_hoje": execucoes_hoje or 0,
        "execucoes_mes": execucoes_mes or 0,
        "dead_letter_pendentes": dead_letter or 0,
    }


async def get_execucoes_admin(periodo: str = "semana", limit: int = 100) -> list[dict]:
    pool = await get_pool()
    desde = _periodo_sql(periodo)
    rows = await pool.fetch(
        f"""
        SELECT e.id, e.grupo_nome, e.remetente, e.acao, e.projeto,
               e.conteudo_resumo, e.resultado, e.erro_detalhe, e.criado_em,
               c.nome AS cliente_nome
        FROM execucoes e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        WHERE e.criado_em >= {desde}
        ORDER BY e.criado_em DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_todos_usuarios() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT u.id, u.email, u.nome, u.papel, u.criado_em, c.nome AS cliente_nome
        FROM usuarios u
        LEFT JOIN clientes c ON c.id = u.cliente_id
        ORDER BY u.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def criar_cliente(nome: str, slug: str, whatsapp_grupo: str, plano: str) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO clientes (nome, slug, whatsapp_grupo, plano)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        nome, slug, whatsapp_grupo, plano,
    )
    return row["id"]


async def criar_usuario_db(
    email: str,
    nome: str,
    senha_hash: str,
    papel: str,
    cliente_id: int | None,
) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO usuarios (email, nome, senha_hash, papel, cliente_id)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        email.lower().strip(), nome, senha_hash, papel, cliente_id,
    )
    return row["id"]


# ── registro de execução (chamado pelo webhook) ─────────────────────────────

async def registrar_execucao_db(
    grupo_id: str,
    grupo_nome: str,
    remetente: str,
    acao: str,
    projeto: str,
    conteudo_resumo: str,
    resultado: str,
    erro_detalhe: str | None = None,
    cliente_id: int | None = None,
) -> int | None:
    """Persiste uma execução no Postgres. Silencioso em caso de falha."""
    try:
        if cliente_id is None:
            cliente_id = await buscar_cliente_por_grupo(grupo_nome)

        pool = await get_pool()
        row = await pool.fetchrow(
            """
            INSERT INTO execucoes
                (cliente_id, grupo_id, grupo_nome, remetente, acao, projeto,
                 conteudo_resumo, resultado, erro_detalhe)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            RETURNING id
            """,
            cliente_id, grupo_id, grupo_nome, remetente, acao, projeto,
            conteudo_resumo[:500] if conteudo_resumo else "",
            resultado,
            erro_detalhe,
        )

        # atualiza última execução na receita correspondente (se existir)
        if cliente_id:
            await pool.execute(
                """
                UPDATE receitas_ativas
                SET ultima_execucao = NOW(),
                    total_execucoes = total_execucoes + 1
                WHERE cliente_id = $1
                  AND LOWER(sistema_destino) != 'quickbooks'
                  AND status = 'ativa'
                  AND nome ILIKE $2
                """,
                cliente_id, f"%{acao.replace('_', ' ')}%",
            )

        return row["id"]
    except Exception as e:
        logger.warning("portal.registrar_execucao_db falhou (não crítico): %s", e)
        return None


async def registrar_briefing_db(
    cliente_id: int | None,
    data_referencia: str,
    conteudo: str,
    numero_destino: str,
    sucesso: bool = True,
) -> int | None:
    """Persiste um briefing enviado. Silencioso em caso de falha."""
    try:
        pool = await get_pool()
        row = await pool.fetchrow(
            """
            INSERT INTO briefings_enviados
                (cliente_id, data_referencia, conteudo, numero_destino, sucesso)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            cliente_id,
            datetime.strptime(data_referencia, "%Y-%m-%d").date() if isinstance(data_referencia, str) else data_referencia,
            conteudo,
            numero_destino,
            sucesso,
        )
        return row["id"]
    except Exception as e:
        logger.warning("portal.registrar_briefing_db falhou (não crítico): %s", e)
        return None

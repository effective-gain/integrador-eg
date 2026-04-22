"""Autenticação do painel — bcrypt + sessão por cookie assinado.

Papéis:
  admin  → equipe EG, acessa tudo
  cliente → acessa apenas dados do seu cliente_id
"""
from __future__ import annotations

from dataclasses import dataclass

import bcrypt
from fastapi import HTTPException, Request, status

from src.db import get_pool


@dataclass
class Usuario:
    id: int
    email: str
    nome: str
    papel: str          # "admin" | "cliente"
    cliente_id: int | None


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_armazenado.encode("utf-8"))
    except ValueError:
        return False


async def autenticar(email: str, senha: str) -> Usuario | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, nome, senha_hash, papel, cliente_id FROM usuarios WHERE email = $1",
        email.lower().strip(),
    )
    if not row:
        return None
    if not verificar_senha(senha, row["senha_hash"]):
        return None
    return Usuario(
        id=row["id"],
        email=row["email"],
        nome=row["nome"],
        papel=row["papel"],
        cliente_id=row["cliente_id"],
    )


async def buscar_por_id(user_id: int) -> Usuario | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, nome, papel, cliente_id FROM usuarios WHERE id = $1",
        user_id,
    )
    if not row:
        return None
    return Usuario(
        id=row["id"],
        email=row["email"],
        nome=row["nome"],
        papel=row["papel"],
        cliente_id=row["cliente_id"],
    )


async def usuario_atual(request: Request) -> Usuario:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")
    usuario = await buscar_por_id(int(user_id))
    if not usuario:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida")
    return usuario


async def usuario_admin(request: Request) -> Usuario:
    """Dependência — exige papel admin."""
    usuario = await usuario_atual(request)
    if usuario.papel != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito à equipe EG")
    return usuario

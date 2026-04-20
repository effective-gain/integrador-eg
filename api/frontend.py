"""Rotas do painel web (login + dashboard)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.auth import Usuario, autenticar, usuario_atual

router = APIRouter()

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class LoginPayload(BaseModel):
    email: str
    senha: str


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@router.post("/api/login")
async def api_login(payload: LoginPayload, request: Request) -> JSONResponse:
    usuario = await autenticar(payload.email, payload.senha)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    request.session["user_id"] = usuario.id
    return JSONResponse({"id": usuario.id, "email": usuario.email, "nome": usuario.nome})


@router.post("/api/logout")
async def api_logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse({"status": "ok"})


@router.get("/api/me")
async def api_me(usuario: Usuario = Depends(usuario_atual)) -> JSONResponse:
    return JSONResponse({"id": usuario.id, "email": usuario.email, "nome": usuario.nome})


@router.get("/api/dashboard")
async def api_dashboard(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
) -> JSONResponse:
    # puxa os componentes já inicializados no lifespan do app principal
    from api.webhook import dead_letter, briefing_scheduler, transcriber, obsidian
    from src.config import settings

    obsidian_ok = await obsidian.health_check()
    return JSONResponse({
        "usuario": {"email": usuario.email, "nome": usuario.nome},
        "ambiente": settings.environment,
        "obsidian": "online" if obsidian_ok else "offline",
        "whisper": "ativo" if transcriber else "inativo",
        "briefing": f"agendado {settings.briefing_hora}" if briefing_scheduler else "inativo",
        "dead_letter_pendentes": dead_letter.total_pendentes(),
        "whatsapp_numero": "+55 31 97224-4045",
    })

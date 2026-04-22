"""Rotas do painel web — login, portal do cliente e painel admin EG."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from src.auth import Usuario, autenticar, hash_senha, usuario_admin, usuario_atual
from src.configuracoes import get_all as cfg_get_all, set_many as cfg_set_many
from src.portal import (
    criar_cliente,
    criar_usuario_db,
    get_briefings_cliente,
    get_execucoes_admin,
    get_execucoes_cliente,
    get_receitas_cliente,
    get_resumo_cliente,
    get_resumo_global,
    get_todos_clientes,
    get_todos_usuarios,
)

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


# ── páginas estáticas ──────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


# ── auth ───────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    email: str
    senha: str


@router.post("/api/login")
async def api_login(payload: LoginPayload, request: Request) -> JSONResponse:
    usuario = await autenticar(payload.email, payload.senha)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    request.session["user_id"] = usuario.id
    return JSONResponse({
        "id": usuario.id,
        "email": usuario.email,
        "nome": usuario.nome,
        "papel": usuario.papel,
        "cliente_id": usuario.cliente_id,
    })


@router.post("/api/logout")
async def api_logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse({"status": "ok"})


@router.get("/api/me")
async def api_me(usuario: Usuario = Depends(usuario_atual)) -> JSONResponse:
    return JSONResponse({
        "id": usuario.id,
        "email": usuario.email,
        "nome": usuario.nome,
        "papel": usuario.papel,
        "cliente_id": usuario.cliente_id,
    })


# ── portal do cliente ──────────────────────────────────────────────────────

@router.get("/api/portal/resumo")
async def portal_resumo(usuario: Usuario = Depends(usuario_atual)) -> JSONResponse:
    cid = _require_cliente_id(usuario)
    data = await get_resumo_cliente(cid)
    return JSONResponse(data)


@router.get("/api/portal/execucoes")
async def portal_execucoes(
    periodo: str = "semana",
    limit: int = 50,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual),
) -> JSONResponse:
    cid = _require_cliente_id(usuario)
    rows = await get_execucoes_cliente(cid, periodo=periodo, limit=limit, offset=offset)
    return JSONResponse({"items": _serializar(rows), "total": len(rows)})


@router.get("/api/portal/receitas")
async def portal_receitas(usuario: Usuario = Depends(usuario_atual)) -> JSONResponse:
    cid = _require_cliente_id(usuario)
    rows = await get_receitas_cliente(cid)
    return JSONResponse({"items": _serializar(rows)})


@router.get("/api/portal/briefings")
async def portal_briefings(
    limit: int = 20,
    usuario: Usuario = Depends(usuario_atual),
) -> JSONResponse:
    cid = _require_cliente_id(usuario)
    rows = await get_briefings_cliente(cid, limit=limit)
    return JSONResponse({"items": _serializar(rows)})


# ── painel admin EG ────────────────────────────────────────────────────────

@router.get("/api/admin/resumo")
async def admin_resumo(_: Usuario = Depends(usuario_admin)) -> JSONResponse:
    data = await get_resumo_global()
    return JSONResponse(data)


@router.get("/api/admin/clientes")
async def admin_clientes(_: Usuario = Depends(usuario_admin)) -> JSONResponse:
    rows = await get_todos_clientes()
    return JSONResponse({"items": _serializar(rows)})


@router.get("/api/admin/execucoes")
async def admin_execucoes(
    periodo: str = "semana",
    limit: int = 100,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    rows = await get_execucoes_admin(periodo=periodo, limit=limit)
    return JSONResponse({"items": _serializar(rows), "total": len(rows)})


@router.get("/api/admin/usuarios")
async def admin_usuarios(_: Usuario = Depends(usuario_admin)) -> JSONResponse:
    rows = await get_todos_usuarios()
    return JSONResponse({"items": _serializar(rows)})


class CriarClientePayload(BaseModel):
    nome: str
    slug: str
    whatsapp_grupo: str = ""
    plano: str = "premium"


@router.post("/api/admin/clientes")
async def admin_criar_cliente(
    payload: CriarClientePayload,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    try:
        cid = await criar_cliente(
            nome=payload.nome,
            slug=payload.slug,
            whatsapp_grupo=payload.whatsapp_grupo,
            plano=payload.plano,
        )
        return JSONResponse({"id": cid, "status": "criado"}, status_code=201)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CriarUsuarioPayload(BaseModel):
    email: str
    nome: str
    senha: str
    papel: str = "cliente"
    cliente_id: int | None = None


@router.post("/api/admin/usuarios")
async def admin_criar_usuario(
    payload: CriarUsuarioPayload,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    try:
        uid = await criar_usuario_db(
            email=payload.email,
            nome=payload.nome,
            senha_hash=hash_senha(payload.senha),
            papel=payload.papel,
            cliente_id=payload.cliente_id,
        )
        return JSONResponse({"id": uid, "status": "criado"}, status_code=201)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── configurações dinâmicas (admin) ──────────────────────────────────────────

@router.get("/api/admin/configuracoes")
async def admin_get_configuracoes(_: Usuario = Depends(usuario_admin)) -> JSONResponse:
    """Retorna todas as configurações. Valores sensíveis são mascarados."""
    data = await cfg_get_all()
    return JSONResponse(data)


class SalvarEmailPayload(BaseModel):
    gmail_user: str = ""
    gmail_app_password: str = ""
    email_remetente_nome: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: str = "587"


@router.post("/api/admin/configuracoes/email")
async def admin_salvar_email(
    payload: SalvarEmailPayload,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    """Salva credenciais de e-mail e reinicializa o EmailSender."""
    dados = {k: v for k, v in payload.model_dump().items() if v}
    ok = await cfg_set_many(dados)
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao salvar no banco")

    # Reinicializa o EmailSender se tiver usuário + senha novos
    usuario = payload.gmail_user
    senha   = payload.gmail_app_password
    status_email = "salvo"

    if usuario and senha and senha != "••••••••":
        try:
            from api.webhook import reinicializar_email
            sucesso, msg = await reinicializar_email(
                usuario=usuario,
                senha=senha,
                host=payload.smtp_host,
                porta=int(payload.smtp_port or 587),
            )
            status_email = "ativo" if sucesso else f"erro: {msg}"
        except Exception as e:
            status_email = f"salvo_sem_teste: {e}"

    return JSONResponse({"status": status_email})


class SalvarWhatsAppPayload(BaseModel):
    evolution_instance: str = ""


@router.post("/api/admin/configuracoes/whatsapp")
async def admin_salvar_whatsapp(
    payload: SalvarWhatsAppPayload,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    """Salva instância Evolution API e reinicializa o WhatsAppClient."""
    if not payload.evolution_instance:
        raise HTTPException(status_code=400, detail="Nome da instância não pode ser vazio")

    ok = await cfg_set_many({"evolution_instance": payload.evolution_instance})
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao salvar no banco")

    try:
        from api.webhook import reinicializar_whatsapp
        sucesso, msg = await reinicializar_whatsapp(payload.evolution_instance)
        status_wa = "ativo" if sucesso else f"erro: {msg}"
    except Exception as e:
        status_wa = f"salvo_sem_reinicio: {e}"

    return JSONResponse({"status": status_wa, "instancia": payload.evolution_instance})


class SalvarBriefingPayload(BaseModel):
    briefing_numero_destino: str = ""
    briefing_hora: str = "08:00"
    briefing_ativo: str = "true"


@router.post("/api/admin/configuracoes/briefing")
async def admin_salvar_briefing(
    payload: SalvarBriefingPayload,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    """Salva configurações do briefing matinal."""
    dados = {k: v for k, v in payload.model_dump().items() if v}
    ok = await cfg_set_many(dados)
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao salvar no banco")
    return JSONResponse({
        "status": "salvo",
        "aviso": "Reinicie o servidor para aplicar as alterações do briefing.",
    })


@router.post("/api/admin/configuracoes/generico")
async def admin_salvar_generico(
    request: Request,
    _: Usuario = Depends(usuario_admin),
) -> JSONResponse:
    """Salva chaves arbitrárias (obsidian, webhook_secret, etc.)."""
    dados: dict = await request.json()
    # Filtra apenas chaves conhecidas e não-vazias
    _CHAVES_PERMITIDAS = {
        "obsidian_api_key", "obsidian_api_url",
        "webhook_secret",
    }
    filtrado = {k: v for k, v in dados.items() if k in _CHAVES_PERMITIDAS and v and v != "••••••••"}
    if not filtrado:
        return JSONResponse({"status": "nenhuma_chave_valida"})

    ok = await cfg_set_many(filtrado)
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao salvar no banco")

    # Se webhook_secret foi alterado, invalida o cache imediatamente
    if "webhook_secret" in filtrado:
        try:
            from api.webhook import resetar_cache_webhook_secret
            resetar_cache_webhook_secret()
        except Exception:
            pass

    return JSONResponse({"status": "salvo", "chaves": list(filtrado.keys())})


@router.post("/api/admin/configuracoes/testar-email")
async def admin_testar_email(_: Usuario = Depends(usuario_admin)) -> JSONResponse:
    """Testa a conexão SMTP com as credenciais atuais."""
    try:
        from api.webhook import email_sender
        if email_sender is None:
            return JSONResponse({"status": "inativo", "mensagem": "E-mail não configurado"})
        ok = await email_sender.health_check()
        return JSONResponse({
            "status": "ok" if ok else "erro",
            "mensagem": "Conexão bem-sucedida" if ok else "Falha na autenticação SMTP",
        })
    except Exception as e:
        return JSONResponse({"status": "erro", "mensagem": str(e)})


# ── dashboard de sistema (admin — mantém compatibilidade) ─────────────────

@router.get("/api/dashboard")
async def api_dashboard(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
) -> JSONResponse:
    from api.webhook import briefing_scheduler, dead_letter, obsidian, outlook_client, transcriber, email_sender
    from src.config import settings

    obsidian_ok = False
    if obsidian is not None:
        try:
            obsidian_ok = await obsidian.health_check()
        except Exception:
            obsidian_ok = False
    try:
        pendentes = await dead_letter.total_pendentes() if settings.database_url else 0
    except Exception:
        pendentes = -1

    # E-mail status
    email_status = "inativo"
    if outlook_client is not None:
        try:
            ol_ok = await outlook_client.health_check()
            email_status = "outlook_ok" if ol_ok else "outlook_erro"
        except Exception:
            email_status = "outlook_erro"
    elif email_sender is not None:
        email_status = "smtp_gmail"

    return JSONResponse({
        "usuario": {"email": usuario.email, "nome": usuario.nome, "papel": usuario.papel},
        "ambiente": settings.environment,
        "obsidian": "online" if obsidian_ok else "offline",
        "whisper": "ativo" if transcriber else "inativo",
        "briefing": f"agendado {settings.briefing_hora}" if briefing_scheduler else "inativo",
        "email": email_status,
        "dead_letter_pendentes": pendentes,
        "whatsapp_numero": "+55 31 97224-4045",
    })


# ── helpers ────────────────────────────────────────────────────────────────

def _require_cliente_id(usuario: Usuario) -> int:
    """Admin pode ver dados sem cliente_id. Cliente precisa ter cliente_id."""
    if usuario.papel == "admin":
        raise HTTPException(
            status_code=400,
            detail="Use /api/admin/* para acesso admin. Portal é para clientes.",
        )
    if usuario.cliente_id is None:
        raise HTTPException(
            status_code=400,
            detail="Usuário não está associado a nenhum cliente.",
        )
    return usuario.cliente_id


def _serializar(rows: list[dict]) -> list[dict]:
    """Converte tipos Python (datetime, date) para string JSON-safe."""
    import json
    from datetime import date, datetime

    result = []
    for row in rows:
        serialized = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                serialized[k] = v.isoformat()
            elif isinstance(v, date):
                serialized[k] = v.isoformat()
            else:
                serialized[k] = v
        result.append(serialized)
    return result

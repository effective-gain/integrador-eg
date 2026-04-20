import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.app_client import AppClient
from src.classifier import Classifier
from src.config import settings
from src.contexto import ContextoConversa, ContextoPendente
from src.db import close_pool
from src.dead_letter import DeadLetterQueue
from src.email_reader import EmailReader
from src.models import AcaoTipo, DiarioEntrada, ACAO_EMOJI
from src.obsidian import ObsidianClient, ObsidianError
from src.scheduler import BriefingScheduler
from src.transcriber import Transcriber, TranscritorError
from src.whatsapp import WhatsAppClient, WhatsAppError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# --- dependências globais ---
classifier: Classifier
obsidian: ObsidianClient
whatsapp: WhatsAppClient
app_client: AppClient
transcriber: Transcriber | None = None
briefing_scheduler: BriefingScheduler | None = None
contexto_conversa: ContextoConversa = ContextoConversa()
dead_letter: DeadLetterQueue = DeadLetterQueue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier, obsidian, whatsapp, transcriber, briefing_scheduler

    classifier = Classifier(api_key=settings.anthropic_api_key)
    obsidian = ObsidianClient(base_url=settings.obsidian_api_url, api_key=settings.obsidian_api_key)
    app_client = AppClient(base_url=settings.app_url, api_key=settings.app_api_key)
    whatsapp = WhatsAppClient(
        base_url=settings.evolution_api_url,
        instance=settings.evolution_instance,
        api_key=settings.evolution_api_key,
    )

    if settings.openai_api_key:
        transcriber = Transcriber(api_key=settings.openai_api_key)
        logger.info("Transcritor Whisper ativado")

    if settings.briefing_numero_destino:
        email_reader = None
        if settings.gmail_user and settings.gmail_app_password:
            email_reader = EmailReader(
                imap_host=settings.gmail_imap_host,
                usuario=settings.gmail_user,
                senha=settings.gmail_app_password,
            )

        import anthropic as _anthropic
        briefing_scheduler = BriefingScheduler(
            obsidian=obsidian,
            whatsapp_send_fn=whatsapp.enviar_mensagem,
            numero_destino=settings.briefing_numero_destino,
            hora=settings.briefing_hora,
            email_reader=email_reader,
            anthropic_client=_anthropic.Anthropic(api_key=settings.anthropic_api_key),
        )
        briefing_scheduler.iniciar()
        logger.info("Briefing agendado para %s → %s", settings.briefing_hora, settings.briefing_numero_destino)

    pendentes = dead_letter.total_pendentes()
    if pendentes:
        logger.warning("Dead letter queue: %d operações pendentes ao iniciar", pendentes)

    logger.info("Integrador EG iniciado ✅")
    yield

    if briefing_scheduler:
        briefing_scheduler.parar()
    await close_pool()
    logger.info("Integrador EG encerrado")


app = FastAPI(title="Integrador EG", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="eg_session",
    same_site="lax",
    https_only=settings.environment == "production",
    max_age=60 * 60 * 8,  # 8h
)

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if _WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")

from api.frontend import router as frontend_router  # noqa: E402
app.include_router(frontend_router)


@app.get("/health")
async def health():
    obsidian_ok = await obsidian.health_check()
    return {
        "status": "ok",
        "obsidian": "ok" if obsidian_ok else "offline",
        "whisper": "ativo" if transcriber else "inativo",
        "briefing": f"agendado {settings.briefing_hora}" if briefing_scheduler else "inativo",
        "dead_letter_pendentes": dead_letter.total_pendentes(),
        "environment": settings.environment,
    }


_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def _verificar_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Rejeita requisições sem x-api-key válida quando WEBHOOK_SECRET está configurado."""
    if not settings.webhook_secret:
        return  # dev mode: sem secret configurado aceita tudo
    if api_key != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


@app.post("/webhook/whatsapp", dependencies=[Depends(_verificar_api_key)])
async def webhook_whatsapp(request: Request):
    payload = await request.json()
    mensagem = WhatsAppClient.parsear_webhook(payload)

    if mensagem is None:
        return JSONResponse({"status": "ignored"}, status_code=status.HTTP_200_OK)

    logger.info("Mensagem recebida | grupo=%s | tipo=%s", mensagem.grupo_nome, mensagem.tipo_original)

    # --- transcrição de áudio ---
    if mensagem.tipo_original == "audio":
        if not transcriber:
            await _responder(mensagem.grupo_id, "⚠️ Transcrição de áudio não configurada.")
            return JSONResponse({"status": "audio_sem_transcricao"})

        if not mensagem.arquivo_url:
            await _responder(mensagem.grupo_id, "⚠️ Não consegui localizar o áudio.")
            return JSONResponse({"status": "audio_sem_url"})

        try:
            audio_bytes = await whatsapp.download_audio(mensagem.arquivo_url)
            mensagem.conteudo = await transcriber.transcrever(audio_bytes)
            logger.info("Áudio transcrito: '%s...'", mensagem.conteudo[:60])
        except (TranscritorError, WhatsAppError) as e:
            logger.error("Falha na transcrição: %s", e)
            await _responder(mensagem.grupo_id, "⚠️ Não consegui transcrever o áudio. Pode enviar em texto?")
            await _registrar_diario(mensagem, AcaoTipo.AMBIGUA, "desconhecido", "erro", str(e))
            return JSONResponse({"status": "transcricao_falhou"})

    # --- contexto de conversa: resposta a esclarecimento pendente ---
    ctx = contexto_conversa.recuperar(mensagem.grupo_id, mensagem.remetente)
    if ctx:
        mensagem.conteudo = (
            f"Contexto anterior: {ctx.conteudo_original}\n"
            f"Pergunta feita: {ctx.pergunta}\n"
            f"Resposta do usuário: {mensagem.conteudo}"
        )
        contexto_conversa.limpar(mensagem.grupo_id, mensagem.remetente)
        logger.info("Contexto de esclarecimento recuperado para %s", mensagem.remetente)

    # --- DNA narrativo do projeto (contexto para o classificador) ---
    projeto_inferido = mensagem.grupo_nome  # fallback antes da classificação
    dna_projeto = ""
    try:
        from src.models import GRUPOS_PROJETOS
        nome_lower = mensagem.grupo_nome.lower()
        for chave, nome in GRUPOS_PROJETOS.items():
            if chave in nome_lower:
                projeto_inferido = nome
                break
        dna_projeto = await obsidian.ler_dna_projeto(projeto_inferido)
    except Exception as e:
        logger.warning("DNA não carregado para '%s': %s", projeto_inferido, e)

    # --- classificação ---
    try:
        resultado = classifier.classificar(mensagem, dna_projeto=dna_projeto)
    except Exception as e:
        logger.error("Erro no classificador: %s", e)
        await _responder(mensagem.grupo_id, "⚠️ Erro interno ao processar a mensagem. O time EG foi notificado.")
        raise HTTPException(status_code=500, detail=str(e))

    # --- se ambígua: salva contexto, pede esclarecimento e encerra ---
    if resultado.requer_esclarecimento:
        pergunta = resultado.pergunta_esclarecimento or "Pode detalhar melhor?"
        contexto_conversa.salvar(
            mensagem.grupo_id,
            mensagem.remetente,
            ContextoPendente(
                pergunta=pergunta,
                conteudo_original=mensagem.conteudo,
                projeto=resultado.projeto,
            ),
        )
        await _responder(mensagem.grupo_id, pergunta)
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "ambigua")
        return JSONResponse({"status": "esclarecimento_solicitado"})

    # --- consultar_tasks: lê Obsidian e responde sem escrever ---
    if resultado.acao == AcaoTipo.CONSULTAR_TASKS:
        try:
            resposta_tasks = await obsidian.consultar_tasks(resultado.projeto)
        except ObsidianError as e:
            logger.error("Erro ao consultar tasks: %s", e)
            await _responder(mensagem.grupo_id, "⚠️ Não consegui acessar o Obsidian agora.")
            return JSONResponse({"status": "obsidian_offline"})
        await _responder(mensagem.grupo_id, resposta_tasks)
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "sucesso")
        return JSONResponse({"status": "ok", "acao": resultado.acao, "projeto": resultado.projeto})

    # --- registra no Obsidian ---
    try:
        caminho = await obsidian.registrar_acao(
            acao=resultado.acao,
            projeto=resultado.projeto,
            conteudo=resultado.conteudo_formatado,
        )
        logger.info("Registrado em Obsidian: %s", caminho)
    except ObsidianError as e:
        logger.error("Erro no Obsidian: %s", e)
        dead_letter.enfileirar(
            grupo_id=mensagem.grupo_id,
            grupo_nome=mensagem.grupo_nome,
            acao=resultado.acao,
            projeto=resultado.projeto,
            conteudo_formatado=resultado.conteudo_formatado,
            erro=str(e),
        )
        await _responder(
            mensagem.grupo_id,
            "⚠️ Obsidian temporariamente indisponível. Sua mensagem foi salva e será registrada assim que voltar.",
        )
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "erro", str(e))
        raise HTTPException(status_code=503, detail=str(e))

    # --- confirma no grupo ---
    emoji = ACAO_EMOJI.get(resultado.acao, "✅")
    await _responder(mensagem.grupo_id, f"{emoji} {resultado.resumo_confirmacao}")

    # --- registra no diário e no dashboard ---
    await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "sucesso")
    await app_client.registrar_execucao(
        grupo_id=mensagem.grupo_id, grupo_nome=mensagem.grupo_nome,
        acao=resultado.acao, projeto=resultado.projeto, resultado="sucesso",
        remetente=mensagem.remetente, conteudo_resumo=mensagem.conteudo[:200],
        dna_usado=bool(dna_projeto),
    )

    return JSONResponse({"status": "ok", "acao": resultado.acao, "projeto": resultado.projeto})


@app.post("/retry", dependencies=[Depends(_verificar_api_key)])
async def retry_dead_letter():
    """Reprocessa operações da dead letter queue. Chamável manualmente ou pelo briefing."""
    pendentes = dead_letter.listar_pendentes()
    if not pendentes:
        return JSONResponse({"status": "ok", "processados": 0, "mensagem": "Fila vazia."})

    sucesso = 0
    falhou = 0

    for item in pendentes:
        try:
            await obsidian.registrar_acao(
                acao=AcaoTipo(item["acao"]),
                projeto=item["projeto"],
                conteudo=item["conteudo_formatado"],
            )
            dead_letter.remover(item["id"])
            sucesso += 1
            logger.info("Dead letter: reprocessado id=%d | %s", item["id"], item["acao"])
        except ObsidianError as e:
            dead_letter.incrementar_tentativas(item["id"], str(e))
            falhou += 1
            logger.warning("Dead letter: falhou novamente id=%d: %s", item["id"], e)

    return JSONResponse({
        "status": "ok",
        "processados": sucesso,
        "falhou": falhou,
        "restantes": dead_letter.total_pendentes(),
    })


async def _responder(grupo_id: str, texto: str) -> None:
    try:
        await whatsapp.enviar_mensagem(grupo_id, texto)
    except WhatsAppError as e:
        logger.error("Falha ao enviar resposta WhatsApp: %s", e)


async def _registrar_diario(mensagem, acao, projeto, resultado, erro=None) -> None:
    try:
        entrada = DiarioEntrada(
            grupo=mensagem.grupo_nome,
            projeto=projeto,
            acao=acao,
            conteudo_resumo=mensagem.conteudo[:120],
            resultado=resultado,
            erro_detalhe=erro,
        )
        await obsidian.registrar_diario(entrada)
    except ObsidianError as e:
        logger.error("CRÍTICO: falha ao registrar diário: %s", e)

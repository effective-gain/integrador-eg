import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.classifier import Classifier
from src.config import settings
from src.models import AcaoTipo, DiarioEntrada, ACAO_EMOJI
from src.obsidian import ObsidianClient, ObsidianError
from src.whatsapp import WhatsAppClient, WhatsAppError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# --- dependências globais ---
classifier: Classifier
obsidian: ObsidianClient
whatsapp: WhatsAppClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier, obsidian, whatsapp
    classifier = Classifier(api_key=settings.anthropic_api_key)
    obsidian = ObsidianClient(base_url=settings.obsidian_api_url, api_key=settings.obsidian_api_key)
    whatsapp = WhatsAppClient(
        base_url=settings.evolution_api_url,
        instance=settings.evolution_instance,
        api_key=settings.evolution_api_key,
    )
    logger.info("Integrador EG iniciado ✅")
    yield
    logger.info("Integrador EG encerrado")


app = FastAPI(title="Integrador EG", lifespan=lifespan)


@app.get("/health")
async def health():
    obsidian_ok = await obsidian.health_check()
    return {
        "status": "ok",
        "obsidian": "ok" if obsidian_ok else "offline",
        "environment": settings.environment,
    }


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    payload = await request.json()
    mensagem = WhatsAppClient.parsear_webhook(payload)

    if mensagem is None:
        # mensagem ignorada (bot, tipo não suportado, DM)
        return JSONResponse({"status": "ignored"}, status_code=status.HTTP_200_OK)

    logger.info("Mensagem recebida | grupo=%s | tipo=%s", mensagem.grupo_nome, mensagem.tipo_original)

    # --- classificação ---
    try:
        resultado = classifier.classificar(mensagem)
    except Exception as e:
        logger.error("Erro no classificador: %s", e)
        await _responder(mensagem.grupo_id, "⚠️ Erro interno ao processar a mensagem. O time EG foi notificado.")
        raise HTTPException(status_code=500, detail=str(e))

    # --- se ambígua: pede esclarecimento e encerra ---
    if resultado.requer_esclarecimento:
        await _responder(mensagem.grupo_id, resultado.pergunta_esclarecimento or "Pode detalhar melhor?")
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "ambigua")
        return JSONResponse({"status": "esclarecimento_solicitado"})

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
        await _responder(mensagem.grupo_id, "⚠️ Não consegui salvar no Obsidian. Tentando novamente em breve.")
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "erro", str(e))
        raise HTTPException(status_code=503, detail=str(e))

    # --- confirma no grupo ---
    emoji = ACAO_EMOJI.get(resultado.acao, "✅")
    await _responder(mensagem.grupo_id, f"{emoji} {resultado.resumo_confirmacao}")

    # --- registra no diário ---
    await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "sucesso")

    return JSONResponse({"status": "ok", "acao": resultado.acao, "projeto": resultado.projeto})


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
        # diário é classe A — loga o erro mas não deixa subir para não mascarar o fluxo
        logger.error("CRÍTICO: falha ao registrar diário: %s", e)

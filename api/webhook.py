import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.app_client import AppClient
from src.bot_status import BotStatus, parsear_comando
from src.classifier import Classifier
from src.config import settings
from src.configuracoes import carregar_para_settings
from src.contexto import ContextoConversa, ContextoPendente
from src.db import close_pool
from src.dead_letter import DeadLetterQueue
from src.email_reader import EmailReader
from src.email_sender import EmailSender
from src.historico import HistoricoConversa
from src.models import AcaoTipo, DiarioEntrada, ACAO_EMOJI
from src.obsidian import ObsidianClient, ObsidianError
from src.outlook_client import OutlookClient
from src.scheduler import BriefingScheduler
from src.transcriber import Transcriber, TranscritorError
from src.whatsapp import WhatsAppClient, WhatsAppError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# --- dependências globais (inicializadas de forma resiliente no lifespan) ---
classifier: Classifier | None = None
obsidian: ObsidianClient | None = None
whatsapp: WhatsAppClient | None = None
app_client: AppClient | None = None
transcriber: Transcriber | None = None
email_sender: EmailSender | None = None       # SMTP fallback (Gmail)
outlook_client: OutlookClient | None = None   # Microsoft Graph API (preferencial)
briefing_scheduler: BriefingScheduler | None = None
contexto_conversa: ContextoConversa = ContextoConversa()
dead_letter: DeadLetterQueue = DeadLetterQueue()
bot_status: BotStatus = BotStatus()
historico_conversa: HistoricoConversa = HistoricoConversa()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier, obsidian, whatsapp, app_client, transcriber, email_sender, outlook_client, briefing_scheduler

    # ── 1. Carregar configurações dinâmicas do banco (sobrepõem o .env) ──────
    cfg: dict[str, str] = {}
    if settings.database_url:
        try:
            cfg = await carregar_para_settings()
            if cfg:
                logger.info("Configurações carregadas do banco: %s chaves", len(cfg))
        except Exception as e:
            logger.warning("Não foi possível carregar configurações do banco: %s", e)

    def _cfg(chave: str, fallback: str = "") -> str:
        """Retorna valor do banco se existir, senão o fallback (.env / padrão)."""
        return cfg.get(chave) or fallback

    # ── 2. Inicializar serviços com valores mesclados ─────────────────────────

    try:
        classifier = Classifier(api_key=settings.anthropic_api_key)
    except Exception as e:
        logger.warning("Classifier não inicializado: %s", e)

    # Obsidian — key e URL podem vir do banco
    _obsidian_key = _cfg("obsidian_api_key", settings.obsidian_api_key)
    _obsidian_url = _cfg("obsidian_api_url", settings.obsidian_api_url)
    try:
        obsidian = ObsidianClient(base_url=_obsidian_url, api_key=_obsidian_key)
        if _obsidian_key:
            logger.info("Obsidian inicializado (%s)", _obsidian_url)
        else:
            logger.warning("Obsidian: API key não configurada")
    except Exception as e:
        logger.warning("Obsidian client não inicializado: %s", e)

    try:
        app_client = AppClient(base_url=settings.app_url, api_key=settings.app_api_key)
    except Exception as e:
        logger.warning("AppClient não inicializado: %s", e)

    # WhatsApp — instância pode vir do banco (configurada pelo portal)
    _wa_instance = _cfg("evolution_instance", settings.evolution_instance)
    try:
        whatsapp = WhatsAppClient(
            base_url=settings.evolution_api_url,
            instance=_wa_instance,
            api_key=settings.evolution_api_key,
        )
        if _wa_instance:
            logger.info("WhatsApp inicializado (instância: %s)", _wa_instance)
        else:
            logger.warning("WhatsApp: instância não configurada")
    except Exception as e:
        logger.warning("WhatsApp client não inicializado: %s", e)

    # SMTP Gmail — credenciais podem vir do banco
    _gmail_user = _cfg("gmail_user", settings.smtp_user or settings.gmail_user)
    _gmail_pass = _cfg("gmail_app_password", settings.smtp_password or settings.gmail_app_password)
    _smtp_host  = _cfg("smtp_host", settings.smtp_host)
    _smtp_port  = int(_cfg("smtp_port", str(settings.smtp_port)))

    if _gmail_user and _gmail_pass:
        try:
            email_sender = EmailSender(
                usuario=_gmail_user,
                senha_app=_gmail_pass,
                smtp_host=_smtp_host,
                smtp_port=_smtp_port,
            )
            logger.info("Email sender SMTP inicializado (%s)", _gmail_user)
        except Exception as e:
            logger.warning("Email sender não inicializado: %s", e)
    else:
        logger.info("Email sender: credenciais não configuradas")

    # Outlook Graph API — opcional, sobrepõe SMTP se configurado
    if settings.outlook_client_id and settings.outlook_client_secret and settings.outlook_tenant_id:
        try:
            outlook_client = OutlookClient(
                client_id=settings.outlook_client_id,
                client_secret=settings.outlook_client_secret,
                tenant_id=settings.outlook_tenant_id,
                user_email=settings.outlook_user_email or _gmail_user,
            )
            ok = await outlook_client.health_check()
            if ok:
                logger.info("Outlook (Graph API) inicializado — %s", settings.outlook_user_email)
            else:
                logger.warning("Outlook Graph API: health_check falhou")
                outlook_client = None
        except Exception as e:
            logger.warning("Outlook client não inicializado: %s", e)
            outlook_client = None

    if settings.openai_api_key:
        try:
            transcriber = Transcriber(api_key=settings.openai_api_key)
            logger.info("Transcritor Whisper ativado")
        except Exception as e:
            logger.warning("Transcriber não inicializado: %s", e)

    is_serverless = bool(os.getenv("VERCEL"))

    # Briefing — número e hora podem vir do banco
    _briefing_numero = _cfg("briefing_numero_destino", settings.briefing_numero_destino)
    _briefing_hora   = _cfg("briefing_hora", settings.briefing_hora)
    _briefing_ativo  = _cfg("briefing_ativo", "true").lower() == "true"

    if _briefing_numero and _briefing_ativo and not is_serverless:
        email_reader = None
        if outlook_client is not None:
            from src.email_reader import OutlookGraphReader
            email_reader = OutlookGraphReader(outlook_client)
            logger.info("Briefing: leitura de e-mail via Outlook Graph API")
        elif _gmail_user and _gmail_pass:
            email_reader = EmailReader(
                imap_host=settings.gmail_imap_host,
                usuario=_gmail_user,
                senha=_gmail_pass,
            )
            logger.info("Briefing: leitura de e-mail via IMAP Gmail")

        import anthropic as _anthropic
        briefing_scheduler = BriefingScheduler(
            obsidian=obsidian,
            whatsapp_send_fn=whatsapp.enviar_mensagem,
            numero_destino=_briefing_numero,
            hora=_briefing_hora,
            email_reader=email_reader,
            anthropic_client=_anthropic.Anthropic(api_key=settings.anthropic_api_key),
        )
        briefing_scheduler.iniciar()
        logger.info("Briefing agendado para %s → %s", _briefing_hora, _briefing_numero)
    elif is_serverless:
        logger.info("Ambiente serverless (Vercel): briefing desativado — use Vercel Cron")

    if settings.database_url:
        try:
            pendentes = await dead_letter.total_pendentes()
            if pendentes:
                logger.warning("Dead letter queue: %d operações pendentes ao iniciar", pendentes)
        except Exception as e:
            logger.warning("Dead letter indisponível ao iniciar: %s", e)

    logger.info("Integrador EG iniciado")
    yield

    if briefing_scheduler:
        briefing_scheduler.parar()
    await close_pool()
    logger.info("Integrador EG encerrado")


# ── Funções de reinicialização (chamadas pelo portal de configurações) ────────

async def reinicializar_email(
    usuario: str,
    senha: str,
    host: str = "smtp.gmail.com",
    porta: int = 587,
) -> tuple[bool, str]:
    """Reinicializa o EmailSender com novas credenciais. Chamado pelo portal admin."""
    global email_sender
    try:
        novo = EmailSender(usuario=usuario, senha_app=senha, smtp_host=host, smtp_port=porta)
        # Testa antes de substituir
        ok = await novo.health_check()
        if not ok:
            return False, "Credenciais inválidas ou servidor SMTP recusou a conexão"
        email_sender = novo
        logger.info("EmailSender reinicializado via portal: %s", usuario)
        return True, "ok"
    except Exception as e:
        logger.error("Falha ao reinicializar EmailSender: %s", e)
        return False, str(e)


def resetar_cache_webhook_secret() -> None:
    """Limpa o cache do webhook secret — forçar releitura do banco na próxima requisição."""
    global _webhook_secret_cache
    _webhook_secret_cache = ""


async def reinicializar_whatsapp(instance: str) -> tuple[bool, str]:
    """Reinicializa o WhatsAppClient com nova instância. Chamado pelo portal admin."""
    global whatsapp
    try:
        novo = WhatsAppClient(
            base_url=settings.evolution_api_url,
            instance=instance,
            api_key=settings.evolution_api_key,
        )
        whatsapp = novo
        logger.info("WhatsAppClient reinicializado via portal: instância=%s", instance)
        return True, "ok"
    except Exception as e:
        logger.error("Falha ao reinicializar WhatsAppClient: %s", e)
        return False, str(e)


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
    # Outlook health
    outlook_status = "inativo"
    if outlook_client is not None:
        try:
            ol_ok = await outlook_client.health_check()
            outlook_status = "ok" if ol_ok else "erro"
        except Exception:
            outlook_status = "erro"
    elif email_sender is not None:
        outlook_status = "smtp_fallback"

    return {
        "status": "ok",
        "obsidian": "ok" if obsidian_ok else "offline",
        "whisper": "ativo" if transcriber else "inativo",
        "briefing": f"agendado {settings.briefing_hora}" if briefing_scheduler else "inativo",
        "email": outlook_status,
        "dead_letter_pendentes": pendentes,
        "grupos_com_historico": historico_conversa.total_grupos(),
        "environment": settings.environment,
    }


_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# Cache em memória do webhook_secret — atualizado quando carregado do banco
_webhook_secret_cache: str = ""


async def _get_webhook_secret() -> str:
    """Retorna o webhook secret: banco > .env > vazio (dev mode)."""
    global _webhook_secret_cache
    if _webhook_secret_cache:
        return _webhook_secret_cache
    # Tenta banco primeiro
    try:
        from src.configuracoes import get_config
        db_secret = await get_config("webhook_secret")
        if db_secret:
            _webhook_secret_cache = db_secret
            return db_secret
    except Exception:
        pass
    # Fallback .env
    return settings.webhook_secret


async def _verificar_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Rejeita requisições sem x-api-key válida quando WEBHOOK_SECRET está configurado."""
    secret = await _get_webhook_secret()
    if not secret:
        return  # dev mode: sem secret configurado aceita tudo
    if api_key != secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


@app.post("/webhook/whatsapp", dependencies=[Depends(_verificar_api_key)])
async def webhook_whatsapp(request: Request):
    payload = await request.json()
    mensagem = WhatsAppClient.parsear_webhook(payload)

    if mensagem is None:
        return JSONResponse({"status": "ignored"}, status_code=status.HTTP_200_OK)

    logger.info("Mensagem recebida | grupo=%s | tipo=%s", mensagem.grupo_nome, mensagem.tipo_original)

    # ── 1. Comandos de controle do bot ──────────────────────────────────────
    comando = parsear_comando(mensagem.conteudo)
    if comando:
        cmd, duracao = comando
        if cmd == "pausar":
            resposta = await bot_status.pausar(mensagem.grupo_id, duracao, por=mensagem.remetente)
        elif cmd == "ativar":
            resposta = await bot_status.ativar(mensagem.grupo_id)
            historico_conversa.limpar(mensagem.grupo_id)
        else:  # status / botstatus
            resposta = await bot_status.status_texto(mensagem.grupo_id)
        await _responder(mensagem.grupo_id, resposta)
        return JSONResponse({"status": "comando_bot", "comando": cmd})

    # ── 2. Verifica se o bot está ativo neste grupo ─────────────────────────
    if not await bot_status.ativo(mensagem.grupo_id):
        logger.info("Bot pausado — mensagem ignorada | grupo=%s", mensagem.grupo_nome)
        return JSONResponse({"status": "bot_pausado"})

    # ── 3. Transcrição de áudio ─────────────────────────────────────────────
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

    # ── 4. Contexto de esclarecimento pendente ──────────────────────────────
    ctx = contexto_conversa.recuperar(mensagem.grupo_id, mensagem.remetente)
    if ctx:
        mensagem.conteudo = (
            f"Contexto anterior: {ctx.conteudo_original}\n"
            f"Pergunta feita: {ctx.pergunta}\n"
            f"Resposta do usuário: {mensagem.conteudo}"
        )
        contexto_conversa.limpar(mensagem.grupo_id, mensagem.remetente)
        logger.info("Contexto de esclarecimento recuperado para %s", mensagem.remetente)

    # ── 5. DNA narrativo do projeto ─────────────────────────────────────────
    projeto_inferido = mensagem.grupo_nome
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

    # ── 6. Histórico multi-turn do grupo ────────────────────────────────────
    historico = historico_conversa.obter(mensagem.grupo_id)

    # ── 7. Classificação via tool calls ─────────────────────────────────────
    try:
        resultado = classifier.classificar(mensagem, dna_projeto=dna_projeto, historico=historico)
    except Exception as e:
        logger.error("Erro no classificador: %s", e)
        await _responder(mensagem.grupo_id, "⚠️ Erro interno ao processar a mensagem. O time EG foi notificado.")
        raise HTTPException(status_code=500, detail=str(e))

    # ── 8. Mensagem ambígua → pede esclarecimento ───────────────────────────
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

    # ── 9. consultar_tasks → lê Obsidian e responde sem escrever ───────────
    if resultado.acao == AcaoTipo.CONSULTAR_TASKS:
        try:
            resposta_tasks = await obsidian.consultar_tasks(resultado.projeto)
        except ObsidianError as e:
            logger.error("Erro ao consultar tasks: %s", e)
            await _responder(mensagem.grupo_id, "⚠️ Não consegui acessar o Obsidian agora.")
            return JSONResponse({"status": "obsidian_offline"})
        await _responder(mensagem.grupo_id, resposta_tasks)
        await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "sucesso")
        if resultado.tool_use_id and resultado.tool_name:
            historico_conversa.adicionar_turno(
                mensagem.grupo_id, mensagem.conteudo,
                resultado.tool_use_id, resultado.tool_name, resultado.tool_input or {},
            )
        return JSONResponse({"status": "ok", "acao": resultado.acao, "projeto": resultado.projeto})

    # ── Bloco de ações de e-mail ─────────────────────────────────────────────
    _ACOES_EMAIL = {
        AcaoTipo.ENVIAR_EMAIL,
        AcaoTipo.RESPONDER_EMAIL,
        AcaoTipo.ENCAMINHAR_EMAIL,
        AcaoTipo.CRIAR_RASCUNHO,
    }

    if resultado.acao in _ACOES_EMAIL:
        # Decide qual cliente de e-mail usar
        usar_outlook = outlook_client is not None
        usar_smtp    = email_sender is not None

        if not usar_outlook and not usar_smtp:
            await _responder(
                mensagem.grupo_id,
                "⚠️ Serviço de e-mail não configurado.\n"
                "Para Outlook: adicione OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID no .env\n"
                "Para Gmail: adicione GMAIL_USER e GMAIL_APP_PASSWORD no .env.",
            )
            return JSONResponse({"status": "email_nao_configurado"})

        para    = resultado.email_para or ""
        assunto = resultado.email_assunto or f"Mensagem de {resultado.projeto}"
        corpo   = resultado.email_corpo or resultado.conteudo_formatado
        tipo    = resultado.email_tipo or "personalizado"
        msg_id  = resultado.email_message_id or ""
        cc      = resultado.email_cc
        bcc     = resultado.email_bcc

        # Para enviar/responder/encaminhar precisamos de destinatário
        if resultado.acao != AcaoTipo.CRIAR_RASCUNHO and not para:
            await _responder(
                mensagem.grupo_id,
                "⚠️ Destinatário do e-mail não identificado. Por favor, informe o endereço de e-mail.",
            )
            return JSONResponse({"status": "email_sem_destinatario"})

        sucesso_email = False
        erro_email: str | None = None
        resumo_wa = ""

        try:
            if usar_outlook:
                # ── Microsoft Graph API ──────────────────────────────
                if resultado.acao == AcaoTipo.ENVIAR_EMAIL:
                    sucesso_email = await outlook_client.enviar_com_template(
                        para=para,
                        assunto=assunto,
                        tipo=tipo,
                        dados={
                            "corpo": corpo,
                            "pergunta": corpo,
                            "cliente": para,
                            "remetente": settings.email_remetente_nome,
                            "descricao": corpo,
                        },
                        cc=cc,
                        bcc=bcc,
                    )
                    resumo_wa = f"📧 E-mail enviado para {para}\n📌 Assunto: {assunto}"

                elif resultado.acao == AcaoTipo.RESPONDER_EMAIL:
                    if not msg_id:
                        await _responder(
                            mensagem.grupo_id,
                            "⚠️ ID da mensagem original não encontrado. Não consigo identificar qual e-mail responder.",
                        )
                        return JSONResponse({"status": "email_sem_message_id"})
                    sucesso_email = await outlook_client.responder(
                        message_id=msg_id,
                        corpo=corpo,
                    )
                    resumo_wa = f"↩️ Resposta enviada\n📌 Assunto: {assunto}"

                elif resultado.acao == AcaoTipo.ENCAMINHAR_EMAIL:
                    if not msg_id:
                        await _responder(
                            mensagem.grupo_id,
                            "⚠️ ID da mensagem original não encontrado. Não consigo identificar qual e-mail encaminhar.",
                        )
                        return JSONResponse({"status": "email_sem_message_id"})
                    destinatarios = [e.strip() for e in para.split(",") if e.strip()]
                    sucesso_email = await outlook_client.encaminhar(
                        message_id=msg_id,
                        para=destinatarios,
                        comentario=corpo,
                    )
                    resumo_wa = f"↪️ E-mail encaminhado para {para}"

                elif resultado.acao == AcaoTipo.CRIAR_RASCUNHO:
                    # Corpo simples → HTML básico para o rascunho
                    corpo_html = f"<p>{corpo.replace(chr(10), '<br/>')}</p>"
                    draft_id = await outlook_client.criar_rascunho(
                        para=para or "",
                        assunto=assunto,
                        corpo_html=corpo_html,
                        corpo_texto=corpo,
                        cc=cc,
                    )
                    sucesso_email = bool(draft_id)
                    resumo_wa = f"📝✉️ Rascunho criado: {assunto}"

            else:
                # ── SMTP Gmail fallback ─────────────────────────────
                if resultado.acao in (AcaoTipo.ENVIAR_EMAIL, AcaoTipo.CRIAR_RASCUNHO):
                    sucesso_email = await email_sender.enviar_com_template(
                        para=para,
                        assunto=assunto,
                        tipo=tipo,
                        dados={
                            "corpo": corpo,
                            "pergunta": corpo,
                            "cliente": para,
                            "remetente": settings.email_remetente_nome,
                            "descricao": corpo,
                        },
                    )
                    resumo_wa = f"📧 E-mail enviado para {para}\n📌 Assunto: {assunto}"
                else:
                    await _responder(
                        mensagem.grupo_id,
                        f"⚠️ Ação '{resultado.acao}' requer Outlook (Graph API). "
                        "Configure OUTLOOK_CLIENT_ID no .env.",
                    )
                    return JSONResponse({"status": "outlook_nao_configurado"})

        except Exception as exc:
            logger.error("Erro ao executar ação de e-mail (%s): %s", resultado.acao, exc)
            sucesso_email = False
            erro_email = str(exc)

        emoji = ACAO_EMOJI.get(resultado.acao, "📧")
        if sucesso_email:
            await _responder(mensagem.grupo_id, f"{emoji} {resumo_wa}")
        else:
            fonte = "Outlook" if usar_outlook else "SMTP"
            await _responder(
                mensagem.grupo_id,
                f"⚠️ Falha ao executar ação de e-mail via {fonte}. "
                + (f"Detalhe: {erro_email}" if erro_email else "Verifique as credenciais."),
            )

        await _registrar_diario(
            mensagem, resultado.acao, resultado.projeto,
            "sucesso" if sucesso_email else "erro",
            None if sucesso_email else (erro_email or "Falha e-mail"),
        )
        from src.portal import registrar_execucao_db
        await registrar_execucao_db(
            grupo_id=mensagem.grupo_id,
            grupo_nome=mensagem.grupo_nome,
            remetente=mensagem.remetente,
            acao=resultado.acao,
            projeto=resultado.projeto,
            conteudo_resumo=f"Para: {para} | Assunto: {assunto}",
            resultado="sucesso" if sucesso_email else "erro",
            erro_detalhe=None if sucesso_email else (erro_email or "Falha e-mail"),
        )
        return JSONResponse({
            "status": "ok" if sucesso_email else "email_falhou",
            "acao": resultado.acao,
            "para": para,
            "assunto": assunto,
            "backend": "outlook" if usar_outlook else "smtp",
        })

    # ── 10. Registra no Obsidian ─────────────────────────────────────────────
    try:
        caminho = await obsidian.registrar_acao(
            acao=resultado.acao,
            projeto=resultado.projeto,
            conteudo=resultado.conteudo_formatado,
        )
        logger.info("Registrado em Obsidian: %s", caminho)
    except ObsidianError as e:
        logger.error("Erro no Obsidian: %s", e)
        await dead_letter.enfileirar(
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
        from src.portal import registrar_execucao_db
        await registrar_execucao_db(
            grupo_id=mensagem.grupo_id,
            grupo_nome=mensagem.grupo_nome,
            remetente=mensagem.remetente,
            acao=resultado.acao,
            projeto=resultado.projeto,
            conteudo_resumo=mensagem.conteudo[:300],
            resultado="erro",
            erro_detalhe=str(e),
        )
        raise HTTPException(status_code=503, detail=str(e))

    # ── 11. Confirma no grupo ───────────────────────────────────────────────
    emoji = ACAO_EMOJI.get(resultado.acao, "✅")
    await _responder(mensagem.grupo_id, f"{emoji} {resultado.resumo_confirmacao}")

    # ── 12. Atualiza histórico multi-turn ───────────────────────────────────
    if resultado.tool_use_id and resultado.tool_name:
        historico_conversa.adicionar_turno(
            mensagem.grupo_id, mensagem.conteudo,
            resultado.tool_use_id, resultado.tool_name, resultado.tool_input or {},
        )

    # ── 13. Registra no diário, portal e dashboard ──────────────────────────
    await _registrar_diario(mensagem, resultado.acao, resultado.projeto, "sucesso")

    # portal: grava no Postgres local (feed do portal do cliente)
    from src.portal import registrar_execucao_db
    await registrar_execucao_db(
        grupo_id=mensagem.grupo_id,
        grupo_nome=mensagem.grupo_nome,
        remetente=mensagem.remetente,
        acao=resultado.acao,
        projeto=resultado.projeto,
        conteudo_resumo=mensagem.conteudo[:300],
        resultado="sucesso",
    )

    # dashboard Next.js externo (opcional — não crítico)
    await app_client.registrar_execucao(
        grupo_id=mensagem.grupo_id, grupo_nome=mensagem.grupo_nome,
        acao=resultado.acao, projeto=resultado.projeto, resultado="sucesso",
        remetente=mensagem.remetente, conteudo_resumo=mensagem.conteudo[:200],
        dna_usado=bool(dna_projeto),
    )

    # ── 14. Lançamento financeiro → notifica dashboard ──────────────────────
    if resultado.acao == AcaoTipo.REGISTRAR_LANCAMENTO and resultado.lancamento_valor:
        await app_client.registrar_lancamento(
            descricao=resultado.conteudo_formatado[:200],
            valor=resultado.lancamento_valor,
            tipo=resultado.lancamento_tipo or "despesa",
            projeto=resultado.projeto,
            grupo_origem=mensagem.grupo_nome,
            categoria=resultado.lancamento_categoria or "",
            fornecedor=resultado.lancamento_fornecedor or "",
            data_vencimento=resultado.lancamento_data_vencimento or "",
        )

    return JSONResponse({"status": "ok", "acao": resultado.acao, "projeto": resultado.projeto})


@app.post("/retry", dependencies=[Depends(_verificar_api_key)])
async def retry_dead_letter():
    """Reprocessa operações da dead letter queue. Chamável manualmente ou pelo briefing."""
    pendentes = await dead_letter.listar_pendentes()
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
            await dead_letter.remover(item["id"])
            sucesso += 1
            logger.info("Dead letter: reprocessado id=%d | %s", item["id"], item["acao"])
        except ObsidianError as e:
            await dead_letter.incrementar_tentativas(item["id"], str(e))
            falhou += 1
            logger.warning("Dead letter: falhou novamente id=%d: %s", item["id"], e)

    return JSONResponse({
        "status": "ok",
        "processados": sucesso,
        "falhou": falhou,
        "restantes": await dead_letter.total_pendentes(),
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

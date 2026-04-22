"""Testa o fluxo completo do webhook FastAPI."""
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.models import AcaoTipo, ClassificacaoResult, Prioridade


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _payload_texto(grupo="gestao-eg", conteudo="registrar nota de reunião"):
    return {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": False,
                "participant": "5531999@s.whatsapp.net",
            },
            "pushName": "Luiz",
            "message": {"conversation": conteudo},
        },
        "groupMetadata": {"subject": grupo},
    }


def _payload_audio():
    return {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": False,
                "participant": "5531999@s.whatsapp.net",
            },
            "pushName": "Luiz",
            "message": {"audioMessage": {
                "url": "https://mmg.whatsapp.net/audio.ogg",
                "mimetype": "audio/ogg",
            }},
        },
        "groupMetadata": {"subject": "gestao-eg"},
    }


def _resultado_criar_nota():
    return ClassificacaoResult(
        acao=AcaoTipo.CRIAR_NOTA,
        projeto="Gestão EG",
        conteudo_formatado="## Nota\n\nconteúdo da nota",
        prioridade=Prioridade.MEDIA,
        resumo_confirmacao="Nota registrada com sucesso",
        tool_use_id="tool_abc123",
        tool_name="criar_nota",
        tool_input={"projeto": "Gestão EG", "conteudo_formatado": "## Nota\n\n...", "resumo_confirmacao": "Nota registrada"},
    )


def _resultado_ambigua():
    return ClassificacaoResult(
        acao=AcaoTipo.AMBIGUA,
        projeto="Gestão EG",
        conteudo_formatado="",
        prioridade=Prioridade.MEDIA,
        requer_esclarecimento=True,
        pergunta_esclarecimento="Pode detalhar o que precisa?",
        resumo_confirmacao="Pode detalhar o que precisa?",
        tool_use_id="tool_amb456",
        tool_name="pedir_esclarecimento",
        tool_input={"projeto": "Gestão EG", "pergunta": "Pode detalhar o que precisa?"},
    )


# ── Contexto de app mockado ───────────────────────────────────────────────────

def _montar_app_mockado(
    classificar_retorno=None,
    obsidian_ok=True,
    transcricao="texto transcrito",
):
    """
    Retorna um TestClient com todas as dependências externas mockadas.
    O lifespan é bypassado — injetamos os mocks diretamente no módulo.
    """
    import api.webhook as wh

    mock_classifier = MagicMock()
    mock_classifier.classificar.return_value = classificar_retorno or _resultado_criar_nota()

    mock_obsidian = MagicMock()
    mock_obsidian.health_check = AsyncMock(return_value=True)
    if obsidian_ok:
        mock_obsidian.registrar_acao = AsyncMock(return_value="04 - Inbox/nota.md")
        mock_obsidian.registrar_diario = AsyncMock()
    else:
        from src.obsidian import ObsidianError
        mock_obsidian.registrar_acao = AsyncMock(side_effect=ObsidianError("offline"))
        mock_obsidian.registrar_diario = AsyncMock()

    mock_obsidian.ler_dna_projeto = AsyncMock(return_value="")
    mock_obsidian.consultar_tasks = AsyncMock(return_value="- [ ] task exemplo")

    mock_whatsapp = MagicMock()
    mock_whatsapp.enviar_mensagem = AsyncMock(return_value=True)
    mock_whatsapp.download_audio = AsyncMock(return_value=b"fake-audio")

    mock_transcriber = MagicMock()
    mock_transcriber.transcrever = AsyncMock(return_value=transcricao)

    mock_app_client = MagicMock()
    mock_app_client.registrar_execucao = AsyncMock(return_value=False)
    mock_app_client.registrar_lancamento = AsyncMock(return_value=False)
    mock_app_client.registrar_lead = AsyncMock(return_value=False)

    # DeadLetterQueue — mock async (Postgres)
    mock_dead_letter = MagicMock()
    mock_dead_letter.enfileirar = AsyncMock(return_value=1)
    mock_dead_letter.listar_pendentes = AsyncMock(return_value=[])
    mock_dead_letter.remover = AsyncMock()
    mock_dead_letter.incrementar_tentativas = AsyncMock()
    mock_dead_letter.total_pendentes = AsyncMock(return_value=0)

    # BotStatus e HistoricoConversa — mocks simples (bot sempre ativo por padrão)
    mock_bot_status = MagicMock()
    mock_bot_status.ativo.return_value = True
    mock_bot_status.pausar.return_value = "⏸️ Bot pausado"
    mock_bot_status.ativar.return_value = "▶️ Bot reativado!"
    mock_bot_status.status_texto.return_value = "✅ Bot ativo"

    mock_historico = MagicMock()
    mock_historico.obter.return_value = []
    mock_historico.adicionar_turno = MagicMock()
    mock_historico.limpar = MagicMock()
    mock_historico.total_grupos.return_value = 0

    wh.classifier = mock_classifier
    wh.obsidian = mock_obsidian
    wh.whatsapp = mock_whatsapp
    wh.transcriber = mock_transcriber
    wh.briefing_scheduler = None
    wh.app_client = mock_app_client
    wh.dead_letter = mock_dead_letter
    wh.bot_status = mock_bot_status
    wh.historico_conversa = mock_historico
    wh.email_sender = None
    wh.outlook_client = None

    return TestClient(wh.app, raise_server_exceptions=False), mock_whatsapp, mock_classifier


# ── Testes: fluxo texto ───────────────────────────────────────────────────────

def test_webhook_texto_sucesso():
    client, mock_wa, mock_clf = _montar_app_mockado()
    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["acao"] == AcaoTipo.CRIAR_NOTA.value
    mock_wa.enviar_mensagem.assert_called_once()


def test_webhook_mensagem_ambigua_pede_esclarecimento():
    client, mock_wa, _ = _montar_app_mockado(classificar_retorno=_resultado_ambigua())
    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 200
    assert resp.json()["status"] == "esclarecimento_solicitado"
    # Deve ter respondido com a pergunta de esclarecimento
    texto_enviado = mock_wa.enviar_mensagem.call_args[0][1]
    assert "detalhar" in texto_enviado.lower()


def test_webhook_ignora_mensagem_do_bot():
    import api.webhook as wh
    client = TestClient(wh.app, raise_server_exceptions=False)
    payload = {
        "data": {
            "key": {"remoteJid": "120363000000@g.us", "fromMe": True},
            "message": {"conversation": "mensagem do bot"},
        }
    }
    resp = client.post("/webhook/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_ignora_dm():
    import api.webhook as wh
    client = TestClient(wh.app, raise_server_exceptions=False)
    payload = {
        "data": {
            "key": {"remoteJid": "5531999999@s.whatsapp.net", "fromMe": False},
            "pushName": "Alguém",
            "message": {"conversation": "oi"},
        }
    }
    resp = client.post("/webhook/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_obsidian_offline_retorna_503():
    client, mock_wa, _ = _montar_app_mockado(obsidian_ok=False)
    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 503
    # Deve ter avisado o grupo
    mock_wa.enviar_mensagem.assert_called_once()
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "Obsidian" in texto


def test_webhook_rejeita_api_key_invalida():
    import api.webhook as wh
    from src.config import settings
    original = settings.webhook_secret
    settings.webhook_secret = "secret-correto"

    client = TestClient(wh.app, raise_server_exceptions=False)
    resp = client.post(
        "/webhook/whatsapp",
        json=_payload_texto(),
        headers={"x-api-key": "chave-errada"},
    )
    assert resp.status_code == 403

    settings.webhook_secret = original


def test_webhook_aceita_api_key_correta():
    client, mock_wa, _ = _montar_app_mockado()
    import api.webhook as wh
    from src.config import settings
    original = settings.webhook_secret
    settings.webhook_secret = "secret-correto"

    resp = client.post(
        "/webhook/whatsapp",
        json=_payload_texto(),
        headers={"x-api-key": "secret-correto"},
    )
    assert resp.status_code == 200
    settings.webhook_secret = original


def test_webhook_sem_secret_configurado_aceita_tudo():
    client, _, _ = _montar_app_mockado()
    from src.config import settings
    settings.webhook_secret = ""  # dev mode: sem secret aceita tudo

    resp = client.post("/webhook/whatsapp", json=_payload_texto())
    assert resp.status_code == 200


def test_webhook_health_check():
    import api.webhook as wh
    wh.obsidian = MagicMock()
    wh.obsidian.health_check = AsyncMock(return_value=True)
    wh.transcriber = None
    wh.briefing_scheduler = None

    client = TestClient(wh.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["obsidian"] == "ok"
    assert data["whisper"] == "inativo"


# ── Testes: fluxo áudio ───────────────────────────────────────────────────────

def test_webhook_audio_transcrito_e_classificado():
    client, mock_wa, mock_clf = _montar_app_mockado(transcricao="reunião confirmada para sexta")
    resp = client.post("/webhook/whatsapp", json=_payload_audio())

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    # Classificador deve ter recebido o texto transcrito
    msg_classificada = mock_clf.classificar.call_args[0][0]
    assert msg_classificada.conteudo == "reunião confirmada para sexta"


def test_webhook_audio_sem_transcriber_avisa():
    import api.webhook as wh
    client, mock_wa, _ = _montar_app_mockado()
    wh.transcriber = None  # sem Whisper configurado

    resp = client.post("/webhook/whatsapp", json=_payload_audio())
    assert resp.status_code == 200
    assert resp.json()["status"] == "audio_sem_transcricao"
    mock_wa.enviar_mensagem.assert_called_once()


def test_webhook_audio_falha_transcricao_avisa_grupo():
    from src.transcriber import TranscritorError
    import api.webhook as wh
    client, mock_wa, _ = _montar_app_mockado()
    wh.transcriber = MagicMock()
    wh.transcriber.transcrever = AsyncMock(side_effect=TranscritorError("timeout"))

    resp = client.post("/webhook/whatsapp", json=_payload_audio())
    assert resp.status_code == 200
    assert resp.json()["status"] == "transcricao_falhou"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "texto" in texto.lower() or "áudio" in texto.lower()


# ── Testes: consultar_tasks ───────────────────────────────────────────────────

def _resultado_consultar_tasks():
    return ClassificacaoResult(
        acao=AcaoTipo.CONSULTAR_TASKS,
        projeto="K2Con",
        conteudo_formatado="",
        prioridade=Prioridade.MEDIA,
        resumo_confirmacao="Tasks consultadas",
    )


def test_webhook_consultar_tasks_responde_sem_escrever():
    import api.webhook as wh
    client, mock_wa, mock_clf = _montar_app_mockado(classificar_retorno=_resultado_consultar_tasks())
    wh.obsidian.consultar_tasks = AsyncMock(return_value="📋 *Tasks pendentes — K2Con*\n\n1. revisar proposta")

    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["acao"] == AcaoTipo.CONSULTAR_TASKS.value
    # deve ter respondido com as tasks
    texto_enviado = mock_wa.enviar_mensagem.call_args[0][1]
    assert "Tasks" in texto_enviado or "K2Con" in texto_enviado
    # NÃO deve ter chamado registrar_acao (só leitura)
    wh.obsidian.registrar_acao.assert_not_called()


def test_webhook_consultar_tasks_obsidian_offline():
    import api.webhook as wh
    from src.obsidian import ObsidianError
    client, mock_wa, mock_clf = _montar_app_mockado(classificar_retorno=_resultado_consultar_tasks())
    wh.obsidian.consultar_tasks = AsyncMock(side_effect=ObsidianError("offline"))

    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 200
    assert resp.json()["status"] == "obsidian_offline"
    mock_wa.enviar_mensagem.assert_called_once()


# ── Testes: contexto de conversa ─────────────────────────────────────────────

def test_webhook_ambigua_salva_contexto_e_responde():
    import api.webhook as wh
    from src.contexto import ContextoConversa
    wh.contexto_conversa = ContextoConversa()  # estado limpo

    client, mock_wa, _ = _montar_app_mockado(classificar_retorno=_resultado_ambigua())
    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 200
    assert resp.json()["status"] == "esclarecimento_solicitado"
    # contexto deve ter sido salvo
    assert wh.contexto_conversa.total() == 1


def test_webhook_resposta_esclarecimento_usa_contexto():
    import api.webhook as wh
    from src.contexto import ContextoConversa, ContextoPendente

    wh.contexto_conversa = ContextoConversa()
    # pré-carregar um contexto pendente para o remetente do payload
    wh.contexto_conversa.salvar(
        "120363000000@g.us",
        "Luiz",
        ContextoPendente(
            pergunta="Qual a data da reunião?",
            conteudo_original="reunião com cliente",
            projeto="K2Con",
        ),
    )

    client, mock_wa, mock_clf = _montar_app_mockado()
    resp = client.post("/webhook/whatsapp", json=_payload_texto(conteudo="sexta às 14h"))

    assert resp.status_code == 200
    # classificador deve ter recebido o conteúdo enriquecido com o contexto
    msg_classificada = mock_clf.classificar.call_args[0][0]
    assert "reunião com cliente" in msg_classificada.conteudo
    assert "sexta às 14h" in msg_classificada.conteudo
    # contexto deve ter sido limpo após uso
    assert wh.contexto_conversa.total() == 0


# ── Testes: dead letter ───────────────────────────────────────────────────────

def test_webhook_obsidian_offline_enfileira_dead_letter():
    import api.webhook as wh

    # Mock da DeadLetterQueue (Postgres async)
    mock_dl = MagicMock()
    mock_dl.enfileirar = AsyncMock(return_value=1)
    mock_dl.total_pendentes = AsyncMock(return_value=1)
    wh.dead_letter = mock_dl

    client, mock_wa, _ = _montar_app_mockado(obsidian_ok=False)
    wh.dead_letter = mock_dl  # reaplica após _montar_app_mockado

    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 503
    mock_dl.enfileirar.assert_called_once()
    # avisa usuário com mensagem diferente do simples "offline"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "salva" in texto.lower() or "registrada" in texto.lower()


def test_retry_endpoint_reprocessa_fila():
    import api.webhook as wh

    pendente = {
        "id": 1, "grupo_id": "g1", "grupo_nome": "Grupo",
        "acao": "criar_nota", "projeto": "K2Con",
        "conteudo_formatado": "## Nota", "tentativas": 0,
    }
    mock_dl = MagicMock()
    mock_dl.listar_pendentes = AsyncMock(return_value=[pendente])
    mock_dl.remover = AsyncMock()
    mock_dl.incrementar_tentativas = AsyncMock()
    mock_dl.total_pendentes = AsyncMock(return_value=0)

    client, _, _ = _montar_app_mockado()
    wh.dead_letter = mock_dl
    wh.obsidian.registrar_acao = AsyncMock(return_value="04 - Inbox/nota.md")

    resp = client.post("/retry")

    assert resp.status_code == 200
    data = resp.json()
    assert data["processados"] == 1
    assert data["restantes"] == 0


def test_health_inclui_dead_letter_pendentes():
    """Health retorna 0 quando DATABASE_URL não está configurado (dev mode)."""
    import api.webhook as wh

    wh.obsidian = MagicMock()
    wh.obsidian.health_check = AsyncMock(return_value=True)
    wh.transcriber = None
    wh.briefing_scheduler = None
    wh.email_sender = None
    wh.outlook_client = None

    mock_dl = MagicMock()
    mock_dl.total_pendentes = AsyncMock(return_value=0)
    wh.dead_letter = mock_dl

    client = TestClient(wh.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    # sem DATABASE_URL, retorna 0 por padrão (dev mode)
    assert "dead_letter_pendentes" in resp.json()


# ── Testes: bot on/off (Feature nova) ────────────────────────────────────────

def test_comando_pausar_responde_e_retorna_comando_bot():
    import api.webhook as wh
    from src.bot_status import BotStatus
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "bs.db"
    wh.bot_status = BotStatus(db_path=tmp)

    client, mock_wa, _ = _montar_app_mockado()
    wh.bot_status = BotStatus(db_path=tmp)  # garante instância real

    resp = client.post("/webhook/whatsapp", json=_payload_texto(conteudo="/pausar"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "comando_bot"
    assert resp.json()["comando"] == "pausar"
    mock_wa.enviar_mensagem.assert_called_once()
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "pausado" in texto.lower()


def test_comando_pausar_com_duracao():
    import api.webhook as wh
    from src.bot_status import BotStatus
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "bs.db"
    wh.bot_status = BotStatus(db_path=tmp)

    client, mock_wa, _ = _montar_app_mockado()
    wh.bot_status = BotStatus(db_path=tmp)

    resp = client.post("/webhook/whatsapp", json=_payload_texto(conteudo="/pausar 2h"))
    assert resp.status_code == 200
    assert resp.json()["comando"] == "pausar"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "2h" in texto


def test_comando_ativar():
    import api.webhook as wh
    from src.bot_status import BotStatus
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "bs.db"
    wh.bot_status = BotStatus(db_path=tmp)
    wh.bot_status.pausar("120363000000@g.us")

    client, mock_wa, _ = _montar_app_mockado()
    wh.bot_status = BotStatus(db_path=tmp)

    resp = client.post("/webhook/whatsapp", json=_payload_texto(conteudo="/ativar"))
    assert resp.status_code == 200
    assert resp.json()["comando"] == "ativar"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "reativado" in texto.lower()


def test_bot_pausado_ignora_mensagens_normais():
    import api.webhook as wh
    from src.bot_status import BotStatus
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "bs.db"
    bs = BotStatus(db_path=tmp)
    bs.pausar("120363000000@g.us")

    client, mock_wa, mock_clf = _montar_app_mockado()
    wh.bot_status = bs

    resp = client.post("/webhook/whatsapp", json=_payload_texto())
    assert resp.status_code == 200
    assert resp.json()["status"] == "bot_pausado"
    # não deve ter classificado nem respondido
    mock_clf.classificar.assert_not_called()
    mock_wa.enviar_mensagem.assert_not_called()


def test_comando_status_bot():
    import api.webhook as wh
    from src.bot_status import BotStatus
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "bs.db"
    wh.bot_status = BotStatus(db_path=tmp)

    client, mock_wa, _ = _montar_app_mockado()
    wh.bot_status = BotStatus(db_path=tmp)

    resp = client.post("/webhook/whatsapp", json=_payload_texto(conteudo="/status"))
    assert resp.status_code == 200
    assert resp.json()["comando"] == "status"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "ativo" in texto.lower()


# ── Testes: historico multi-turn (Feature nova) ──────────────────────────────

def test_historico_atualizado_apos_classificacao_sucesso():
    import api.webhook as wh
    from src.historico import HistoricoConversa

    wh.historico_conversa = HistoricoConversa()
    client, _, _ = _montar_app_mockado()
    wh.historico_conversa = HistoricoConversa()

    resp = client.post("/webhook/whatsapp", json=_payload_texto())
    assert resp.status_code == 200
    # histórico deve ter sido atualizado com 1 turno (3 blocos)
    msgs = wh.historico_conversa.obter("120363000000@g.us")
    assert len(msgs) == 3


def test_historico_passado_ao_classificador():
    """O classificador deve receber o histórico existente do grupo."""
    import api.webhook as wh
    from src.historico import HistoricoConversa

    hist = HistoricoConversa()
    # pré-popula um turno anterior
    hist.adicionar_turno(
        "120363000000@g.us",
        "mensagem anterior",
        "tid_prev",
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"},
    )

    client, _, mock_clf = _montar_app_mockado()
    wh.historico_conversa = hist

    resp = client.post("/webhook/whatsapp", json=_payload_texto())
    assert resp.status_code == 200

    # classificar deve ter sido chamado com historico não vazio
    kwargs = mock_clf.classificar.call_args[1]
    assert "historico" in kwargs
    assert len(kwargs["historico"]) == 3  # 1 turno anterior = 3 blocos


def test_health_inclui_grupos_com_historico():
    import api.webhook as wh
    from src.historico import HistoricoConversa

    hist = HistoricoConversa()
    hist.adicionar_turno("g1", "msg", "t1", "criar_nota", {
        "projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    wh.historico_conversa = hist
    wh.obsidian = MagicMock()
    wh.obsidian.health_check = AsyncMock(return_value=True)
    wh.transcriber = None
    wh.briefing_scheduler = None
    wh.email_sender = None
    wh.outlook_client = None

    mock_dl = MagicMock()
    mock_dl.total_pendentes = AsyncMock(return_value=0)
    wh.dead_letter = mock_dl

    client = TestClient(wh.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["grupos_com_historico"] == 1

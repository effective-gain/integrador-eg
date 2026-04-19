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

    wh.classifier = mock_classifier
    wh.obsidian = mock_obsidian
    wh.whatsapp = mock_whatsapp
    wh.transcriber = mock_transcriber
    wh.briefing_scheduler = None
    wh.app_client = mock_app_client

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
    from src.dead_letter import DeadLetterQueue
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "dl.db"
    wh.dead_letter = DeadLetterQueue(db_path=tmp)

    client, mock_wa, _ = _montar_app_mockado(obsidian_ok=False)
    resp = client.post("/webhook/whatsapp", json=_payload_texto())

    assert resp.status_code == 503
    assert wh.dead_letter.total_pendentes() == 1
    # avisa usuário com mensagem diferente do simples "offline"
    texto = mock_wa.enviar_mensagem.call_args[0][1]
    assert "salva" in texto.lower() or "registrada" in texto.lower()


def test_retry_endpoint_reprocessa_fila():
    import api.webhook as wh
    from src.dead_letter import DeadLetterQueue
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "dl.db"
    wh.dead_letter = DeadLetterQueue(db_path=tmp)
    wh.dead_letter.enfileirar("g1", "Grupo", "criar_nota", "K2Con", "## Nota", "timeout anterior")

    client, _, _ = _montar_app_mockado()
    wh.obsidian.registrar_acao = AsyncMock(return_value="04 - Inbox/nota.md")

    resp = client.post("/retry")

    assert resp.status_code == 200
    data = resp.json()
    assert data["processados"] == 1
    assert data["restantes"] == 0


def test_health_inclui_dead_letter_pendentes():
    import api.webhook as wh
    from src.dead_letter import DeadLetterQueue
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp()) / "dl.db"
    wh.dead_letter = DeadLetterQueue(db_path=tmp)
    wh.dead_letter.enfileirar("g1", "G", "criar_nota", "P", "c", "e")

    wh.obsidian = MagicMock()
    wh.obsidian.health_check = AsyncMock(return_value=True)
    wh.transcriber = None
    wh.briefing_scheduler = None

    client = TestClient(wh.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["dead_letter_pendentes"] == 1

import json
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from src.classifier import Classifier, _projeto_do_grupo, _parse_resultado, _montar_system_blocks
from src.models import AcaoTipo, MensagemEntrada, ClassificacaoResult


# --- testes de mapeamento de grupo ---

def test_projeto_do_grupo_conhecido():
    assert _projeto_do_grupo("k2con") == "K2Con"
    assert _projeto_do_grupo("K2CON operacional") == "K2Con"
    assert _projeto_do_grupo("gestao-eg") == "Gestão EG"


def test_projeto_do_grupo_desconhecido():
    resultado = _projeto_do_grupo("grupo-xpto")
    assert resultado == "grupo-xpto"  # fallback: usa o nome do grupo


# --- testes de parse do JSON retornado pelo Claude ---

def test_parse_resultado_valido():
    raw = json.dumps({
        "acao": "criar_nota",
        "projeto": "K2Con",
        "conteudo_formatado": "## Nota\n\n- item",
        "prioridade": "media",
        "requer_esclarecimento": False,
        "pergunta_esclarecimento": None,
        "resumo_confirmacao": "Nota criada 📝",
        "idioma_detectado": "pt",
    })
    resultado = _parse_resultado(raw, "K2Con")
    assert resultado.acao == AcaoTipo.CRIAR_NOTA
    assert resultado.requer_esclarecimento is False
    assert resultado.resumo_confirmacao == "Nota criada 📝"


def test_parse_resultado_json_invalido_retorna_ambigua():
    resultado = _parse_resultado("isso não é json", "K2Con")
    assert resultado.acao == AcaoTipo.AMBIGUA
    assert resultado.requer_esclarecimento is True


def test_parse_resultado_acao_invalida_retorna_ambigua():
    raw = json.dumps({
        "acao": "acao_que_nao_existe",
        "projeto": "K2Con",
        "conteudo_formatado": "x",
        "resumo_confirmacao": "x",
    })
    resultado = _parse_resultado(raw, "K2Con")
    assert resultado.acao == AcaoTipo.AMBIGUA


def test_parse_resultado_ambigua_com_pergunta():
    raw = json.dumps({
        "acao": "ambigua",
        "projeto": "K2Con",
        "conteudo_formatado": "",
        "prioridade": "media",
        "requer_esclarecimento": True,
        "pergunta_esclarecimento": "Qual é a data da reunião?",
        "resumo_confirmacao": "Qual é a data da reunião?",
        "idioma_detectado": "pt",
    })
    resultado = _parse_resultado(raw, "K2Con")
    assert resultado.acao == AcaoTipo.AMBIGUA
    assert resultado.requer_esclarecimento is True
    assert resultado.pergunta_esclarecimento == "Qual é a data da reunião?"


# --- testes do classificador com mock do Claude ---

def _make_mensagem(conteudo: str, grupo: str = "gestao-eg") -> MensagemEntrada:
    return MensagemEntrada(
        grupo_id=f"{grupo}@g.us",
        grupo_nome=grupo,
        remetente="Luiz",
        conteudo=conteudo,
        timestamp=datetime(2026, 4, 17, 10, 0),
    )


def _mock_anthropic_response(raw_json: str):
    mock_content = MagicMock()
    mock_content.text = raw_json
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_criar_nota(mock_anthropic_cls):
    raw = json.dumps({
        "acao": "criar_nota",
        "projeto": "Gestão EG",
        "conteudo_formatado": "## Nota\n\nreunião com fornecedor",
        "prioridade": "media",
        "requer_esclarecimento": False,
        "pergunta_esclarecimento": None,
        "resumo_confirmacao": "Nota criada 📝",
        "idioma_detectado": "pt",
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("reunião com fornecedor amanhã"))

    assert resultado.acao == AcaoTipo.CRIAR_NOTA
    assert resultado.requer_esclarecimento is False
    mock_client.messages.create.assert_called_once()


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_mensagem_ambigua(mock_anthropic_cls):
    raw = json.dumps({
        "acao": "ambigua",
        "projeto": "Gestão EG",
        "conteudo_formatado": "",
        "prioridade": "media",
        "requer_esclarecimento": True,
        "pergunta_esclarecimento": "Qual é a pauta da reunião?",
        "resumo_confirmacao": "Qual é a pauta da reunião?",
        "idioma_detectado": "pt",
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("reunião"))

    assert resultado.acao == AcaoTipo.AMBIGUA
    assert resultado.requer_esclarecimento is True
    assert resultado.pergunta_esclarecimento is not None


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_idioma_espanhol(mock_anthropic_cls):
    raw = json.dumps({
        "acao": "criar_task",
        "projeto": "K2Con",
        "conteudo_formatado": "## Tarea\n\n- revisar contrato",
        "prioridade": "alta",
        "requer_esclarecimento": False,
        "pergunta_esclarecimento": None,
        "resumo_confirmacao": "Tarea agregada: revisar contrato ✅",
        "idioma_detectado": "es",
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("necesito revisar el contrato hoy", grupo="k2con"))

    assert resultado.idioma_detectado == "es"
    assert resultado.acao == AcaoTipo.CRIAR_TASK


# --- testes do DNA-aware classifier ---

def test_system_blocks_sem_dna_retorna_um_bloco():
    blocos = _montar_system_blocks("")
    assert len(blocos) == 1
    assert blocos[0]["cache_control"] == {"type": "ephemeral"}


def test_system_blocks_com_dna_retorna_dois_blocos():
    dna = "# K2Con\n\nProjeto de software para mercado B2B."
    blocos = _montar_system_blocks(dna)
    assert len(blocos) == 2
    assert "DNA DO PROJETO" in blocos[1]["text"]
    assert "K2Con" in blocos[1]["text"]
    assert blocos[1]["cache_control"] == {"type": "ephemeral"}


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_passa_dna_no_system(mock_anthropic_cls):
    raw = json.dumps({
        "acao": "criar_nota",
        "projeto": "K2Con",
        "conteudo_formatado": "## Nota\n\nconteúdo",
        "prioridade": "media",
        "requer_esclarecimento": False,
        "pergunta_esclarecimento": None,
        "resumo_confirmacao": "Nota criada 📝",
        "idioma_detectado": "pt",
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    dna = "# K2Con\n\nCliente de software. Fase atual: Diagnóstico."
    clf.classificar(_make_mensagem("registrar progresso", grupo="k2con"), dna_projeto=dna)

    call_kwargs = mock_client.messages.create.call_args[1]
    system_blocks = call_kwargs["system"]
    assert len(system_blocks) == 2
    assert "DNA DO PROJETO" in system_blocks[1]["text"]


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_sem_dna_usa_um_bloco(mock_anthropic_cls):
    raw = json.dumps({
        "acao": "criar_nota",
        "projeto": "K2Con",
        "conteudo_formatado": "## Nota",
        "prioridade": "media",
        "requer_esclarecimento": False,
        "pergunta_esclarecimento": None,
        "resumo_confirmacao": "Nota criada 📝",
        "idioma_detectado": "pt",
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    clf.classificar(_make_mensagem("nota rápida", grupo="k2con"), dna_projeto="")

    call_kwargs = mock_client.messages.create.call_args[1]
    system_blocks = call_kwargs["system"]
    assert len(system_blocks) == 1  # sem DNA, só instruções

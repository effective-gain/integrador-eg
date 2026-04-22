"""Testa o Classifier com tool calls nativos (Anthropic API)."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.classifier import Classifier, _projeto_do_grupo, _montar_system_blocks, _resultado_de_tool
from src.models import AcaoTipo, MensagemEntrada, ClassificacaoResult


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_mensagem(conteudo: str, grupo: str = "gestao-eg") -> MensagemEntrada:
    return MensagemEntrada(
        grupo_id=f"{grupo}@g.us",
        grupo_nome=grupo,
        remetente="Luiz",
        conteudo=conteudo,
        timestamp=datetime(2026, 4, 17, 10, 0),
    )


def _mock_tool_response(tool_name: str, tool_input: dict, tool_use_id: str = "tool_abc"):
    """Simula uma resposta da Anthropic API com tool_use."""
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = tool_name
    mock_block.input = tool_input
    mock_block.id = tool_use_id

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    return mock_response


def _mock_no_tool_response():
    """Simula resposta sem tool call (fallback para AMBIGUA)."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Não entendi"
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    return mock_response


# ── _projeto_do_grupo ──────────────────────────────────────────────────────────

def test_projeto_do_grupo_conhecido():
    assert _projeto_do_grupo("k2con") == "K2Con"
    assert _projeto_do_grupo("K2CON operacional") == "K2Con"
    assert _projeto_do_grupo("gestao-eg") == "Gestão EG"


def test_projeto_do_grupo_desconhecido():
    resultado = _projeto_do_grupo("grupo-xpto")
    assert resultado == "grupo-xpto"


# ── _resultado_de_tool ─────────────────────────────────────────────────────────

def test_resultado_de_tool_criar_nota():
    r = _resultado_de_tool(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "Nota criada 📝", "prioridade": "media"},
        "tid1",
        "K2Con",
    )
    assert r.acao == AcaoTipo.CRIAR_NOTA
    assert r.projeto == "K2Con"
    assert r.resumo_confirmacao == "Nota criada 📝"
    assert r.tool_use_id == "tid1"
    assert r.tool_name == "criar_nota"
    assert r.requer_esclarecimento is False


def test_resultado_de_tool_pedir_esclarecimento():
    r = _resultado_de_tool(
        "pedir_esclarecimento",
        {"projeto": "K2Con", "pergunta": "Qual é a data da reunião?"},
        "tid2",
        "K2Con",
    )
    assert r.acao == AcaoTipo.AMBIGUA
    assert r.requer_esclarecimento is True
    assert r.pergunta_esclarecimento == "Qual é a data da reunião?"


def test_resultado_de_tool_registrar_lancamento():
    r = _resultado_de_tool(
        "registrar_lancamento",
        {
            "projeto": "EG Food",
            "conteudo_formatado": "## Lançamento",
            "resumo_confirmacao": "Lançamento registrado 💰",
            "valor": 1500.0,
            "tipo": "despesa",
            "categoria": "fornecedor",
            "fornecedor": "Distribuidora X",
        },
        "tid3",
        "EG Food",
    )
    assert r.acao == AcaoTipo.REGISTRAR_LANCAMENTO
    assert r.lancamento_valor == 1500.0
    assert r.lancamento_tipo == "despesa"
    assert r.lancamento_fornecedor == "Distribuidora X"


def test_resultado_de_tool_consultar_tasks():
    r = _resultado_de_tool(
        "consultar_tasks",
        {"projeto": "K2Con", "resumo_confirmacao": "Consultando tasks..."},
        "tid4",
        "K2Con",
    )
    assert r.acao == AcaoTipo.CONSULTAR_TASKS
    assert r.conteudo_formatado == ""


# ── _montar_system_blocks ──────────────────────────────────────────────────────

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


# ── Classifier com mock da API ─────────────────────────────────────────────────

@patch("src.classifier.anthropic.Anthropic")
def test_classificador_criar_nota(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "Gestão EG", "conteudo_formatado": "## Nota\n\nconteúdo", "resumo_confirmacao": "Nota criada 📝"},
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("reunião com fornecedor amanhã"))

    assert resultado.acao == AcaoTipo.CRIAR_NOTA
    assert resultado.requer_esclarecimento is False
    mock_client.messages.create.assert_called_once()


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_mensagem_ambigua(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "pedir_esclarecimento",
        {"projeto": "Gestão EG", "pergunta": "Qual é a pauta da reunião?"},
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("reunião"))

    assert resultado.acao == AcaoTipo.AMBIGUA
    assert resultado.requer_esclarecimento is True
    assert resultado.pergunta_esclarecimento == "Qual é a pauta da reunião?"


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_sem_tool_retorna_fallback_ambigua(mock_anthropic_cls):
    """Se a API não retornar tool call, cai no fallback AMBIGUA."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_no_tool_response()
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("mensagem estranha"))

    assert resultado.acao == AcaoTipo.AMBIGUA
    assert resultado.requer_esclarecimento is True


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_registrar_lancamento_extrai_valor(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "registrar_lancamento",
        {
            "projeto": "EG Food",
            "conteudo_formatado": "## Lançamento\n\nR$ 2.500,00 — Fornecedor ABC",
            "resumo_confirmacao": "Lançamento registrado 💰",
            "valor": 2500.0,
            "tipo": "despesa",
            "categoria": "fornecedor",
            "fornecedor": "ABC Ltda",
        },
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("pagar fornecedor ABC 2500", grupo="beef-smash"))

    assert resultado.acao == AcaoTipo.REGISTRAR_LANCAMENTO
    assert resultado.lancamento_valor == 2500.0
    assert resultado.lancamento_tipo == "despesa"
    assert resultado.lancamento_fornecedor == "ABC Ltda"


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_passa_dna_no_system(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "Nota criada 📝"},
    )
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
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "Nota criada 📝"},
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    clf.classificar(_make_mensagem("nota rápida", grupo="k2con"), dna_projeto="")

    call_kwargs = mock_client.messages.create.call_args[1]
    assert len(call_kwargs["system"]) == 1


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_usa_tool_choice_any(mock_anthropic_cls):
    """Garante que tool_choice={'type':'any'} é sempre enviado."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "ok"},
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    clf.classificar(_make_mensagem("qualquer coisa"))

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["tool_choice"] == {"type": "any"}


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_passa_historico_nas_messages(mock_anthropic_cls):
    """O histórico deve ser prefixado no array de messages."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "ok"},
    )
    mock_anthropic_cls.return_value = mock_client

    historico = [
        {"role": "user", "content": "mensagem anterior"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "criar_nota", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
    ]

    clf = Classifier(api_key="fake")
    clf.classificar(_make_mensagem("nova mensagem"), historico=historico)

    call_kwargs = mock_client.messages.create.call_args[1]
    messages = call_kwargs["messages"]
    # Deve ter os 3 blocos do histórico + a mensagem atual
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "mensagem anterior"
    assert messages[-1]["role"] == "user"
    assert "nova mensagem" in messages[-1]["content"]


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_sem_historico_usa_apenas_mensagem_atual(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_nota",
        {"projeto": "K2Con", "conteudo_formatado": "## Nota", "resumo_confirmacao": "ok"},
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    clf.classificar(_make_mensagem("mensagem sem histórico"))

    call_kwargs = mock_client.messages.create.call_args[1]
    messages = call_kwargs["messages"]
    assert len(messages) == 1  # só a mensagem atual


@patch("src.classifier.anthropic.Anthropic")
def test_classificador_tool_use_id_no_resultado(mock_anthropic_cls):
    """O resultado deve carregar o tool_use_id para o histórico."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(
        "criar_task",
        {"projeto": "K2Con", "conteudo_formatado": "- [ ] task", "resumo_confirmacao": "Task criada ✅"},
        tool_use_id="toolu_xyz789",
    )
    mock_anthropic_cls.return_value = mock_client

    clf = Classifier(api_key="fake")
    resultado = clf.classificar(_make_mensagem("criar task revisar proposta", grupo="k2con"))

    assert resultado.tool_use_id == "toolu_xyz789"
    assert resultado.tool_name == "criar_task"
    assert resultado.acao == AcaoTipo.CRIAR_TASK

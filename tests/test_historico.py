"""Testa HistoricoConversa — thread persistente por grupo."""
from datetime import datetime, timedelta

import pytest

from src.historico import HistoricoConversa


@pytest.fixture
def hist():
    return HistoricoConversa(max_pares=3, ttl_horas=2)


def test_historico_vazio_por_padrao(hist):
    assert hist.obter("grupo-1") == []


def test_adicionar_turno_e_obter(hist):
    hist.adicionar_turno(
        "grupo-1",
        mensagem_usuario="cria uma nota sobre o projeto",
        tool_use_id="tool_abc123",
        tool_name="criar_nota",
        tool_input={"projeto": "K2Con", "conteudo_formatado": "## Nota\n...", "resumo_confirmacao": "Nota criada"},
    )
    msgs = hist.obter("grupo-1")
    # Deve ter 3 blocos: user msg + assistant tool_use + user tool_result
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user"


def test_estrutura_blocos(hist):
    hist.adicionar_turno(
        "grupo-1", "msg", "tid1", "criar_task", {"projeto": "EG", "conteudo_formatado": "x", "resumo_confirmacao": "ok"}
    )
    msgs = hist.obter("grupo-1")
    # bloco assistant tem type=tool_use
    assert msgs[1]["content"][0]["type"] == "tool_use"
    assert msgs[1]["content"][0]["name"] == "criar_task"
    assert msgs[1]["content"][0]["id"] == "tid1"
    # bloco tool_result
    assert msgs[2]["content"][0]["type"] == "tool_result"
    assert msgs[2]["content"][0]["tool_use_id"] == "tid1"


def test_multiplos_turnos(hist):
    for i in range(2):
        hist.adicionar_turno("grupo-1", f"msg {i}", f"tid{i}", "criar_nota", {
            "projeto": "K2Con", "conteudo_formatado": f"nota {i}", "resumo_confirmacao": "ok"
        })
    msgs = hist.obter("grupo-1")
    assert len(msgs) == 6  # 2 turnos × 3 blocos


def test_truncagem_por_max_pares(hist):
    """Com max_pares=3, ao adicionar 4 turnos deve truncar para 3."""
    for i in range(4):
        hist.adicionar_turno("grupo-1", f"msg {i}", f"tid{i}", "criar_nota", {
            "projeto": "K2Con", "conteudo_formatado": f"nota {i}", "resumo_confirmacao": "ok"
        })
    msgs = hist.obter("grupo-1")
    assert len(msgs) == 9  # 3 turnos × 3 blocos (truncou o mais antigo)


def test_grupos_independentes(hist):
    hist.adicionar_turno("grupo-A", "msg A", "ta1", "criar_nota", {
        "projeto": "A", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    assert hist.obter("grupo-A") != []
    assert hist.obter("grupo-B") == []


def test_limpar_grupo(hist):
    hist.adicionar_turno("grupo-1", "msg", "tid1", "criar_nota", {
        "projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    hist.limpar("grupo-1")
    assert hist.obter("grupo-1") == []


def test_expiracao_por_ttl(hist):
    """Histórico não acessado por mais de TTL deve retornar vazio."""
    hist.adicionar_turno("grupo-1", "msg", "tid1", "criar_nota", {
        "projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    # Simula inatividade além do TTL
    h = hist._store["grupo-1"]
    h.ultima_atividade = datetime.now() - timedelta(hours=3)

    assert hist.obter("grupo-1") == []


def test_total_grupos(hist):
    assert hist.total_grupos() == 0
    hist.adicionar_turno("grupo-A", "msg", "tid1", "criar_nota", {
        "projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    hist.adicionar_turno("grupo-B", "msg", "tid2", "criar_task", {
        "projeto": "K2Con", "conteudo_formatado": "x", "resumo_confirmacao": "ok"
    })
    assert hist.total_grupos() == 2

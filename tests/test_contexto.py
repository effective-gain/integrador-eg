from datetime import datetime, timedelta
from unittest.mock import patch

from src.contexto import ContextoConversa, ContextoPendente


def _ctx(conteudo="msg original", pergunta="Qual a data?", projeto="K2Con"):
    return ContextoPendente(pergunta=pergunta, conteudo_original=conteudo, projeto=projeto)


def test_salvar_e_recuperar():
    cc = ContextoConversa()
    cc.salvar("grupo1", "user1", _ctx())
    ctx = cc.recuperar("grupo1", "user1")
    assert ctx is not None
    assert ctx.pergunta == "Qual a data?"


def test_recuperar_chave_inexistente_retorna_none():
    cc = ContextoConversa()
    assert cc.recuperar("grupo_x", "user_x") is None


def test_limpar_remove_contexto():
    cc = ContextoConversa()
    cc.salvar("grupo1", "user1", _ctx())
    cc.limpar("grupo1", "user1")
    assert cc.recuperar("grupo1", "user1") is None


def test_contexto_expirado_retorna_none():
    cc = ContextoConversa(ttl_minutos=5)
    ctx_expirado = ContextoPendente(
        pergunta="?",
        conteudo_original="x",
        projeto="P",
        criado_em=datetime.now() - timedelta(minutes=6),
    )
    cc.salvar("grupo1", "user1", ctx_expirado)
    assert cc.recuperar("grupo1", "user1") is None


def test_contextos_isolados_por_chave():
    cc = ContextoConversa()
    cc.salvar("grupo1", "user1", _ctx(pergunta="A?"))
    cc.salvar("grupo1", "user2", _ctx(pergunta="B?"))
    assert cc.recuperar("grupo1", "user1").pergunta == "A?"
    assert cc.recuperar("grupo1", "user2").pergunta == "B?"


def test_total_conta_apenas_validos():
    cc = ContextoConversa(ttl_minutos=5)
    cc.salvar("g1", "u1", _ctx())
    cc.salvar("g1", "u2", _ctx())
    assert cc.total() == 2
    cc.limpar("g1", "u1")
    assert cc.total() == 1

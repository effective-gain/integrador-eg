import pytest
from datetime import datetime
from src.models import (
    AcaoTipo, Prioridade, MensagemEntrada, ClassificacaoResult,
    GRUPOS_PROJETOS, ACAO_DESTINO, ACAO_EMOJI
)


def test_todos_os_tipos_de_acao_tem_destino():
    acoes_com_destino = set(ACAO_DESTINO.keys())
    acoes_reais = {a for a in AcaoTipo if a != AcaoTipo.AMBIGUA}
    assert acoes_reais == acoes_com_destino, f"Ações sem destino: {acoes_reais - acoes_com_destino}"


def test_todos_os_tipos_de_acao_tem_emoji():
    acoes_com_emoji = set(ACAO_EMOJI.keys())
    acoes_reais = {a for a in AcaoTipo if a != AcaoTipo.AMBIGUA}
    assert acoes_reais == acoes_com_emoji, f"Ações sem emoji: {acoes_reais - acoes_com_emoji}"


def test_grupos_projetos_nao_vazio():
    assert len(GRUPOS_PROJETOS) > 0


def test_mensagem_entrada_defaults():
    msg = MensagemEntrada(
        grupo_id="123@g.us",
        grupo_nome="k2con",
        remetente="Luiz",
        conteudo="preciso registrar uma nota",
    )
    assert msg.tipo_original == "text"
    assert isinstance(msg.timestamp, datetime)
    assert msg.arquivo_url is None


def test_classificacao_result_ambigua_valida():
    r = ClassificacaoResult(
        acao=AcaoTipo.AMBIGUA,
        projeto="K2Con",
        conteudo_formatado="texto",
        requer_esclarecimento=True,
        pergunta_esclarecimento="Pode detalhar?",
        resumo_confirmacao="Pode detalhar?",
    )
    assert r.requer_esclarecimento is True
    assert r.acao == AcaoTipo.AMBIGUA


def test_acao_destino_tem_placeholders():
    for acao, template in ACAO_DESTINO.items():
        formatted = template.format(data="2026-04-17", projeto="K2Con")
        assert "{" not in formatted, f"Template com placeholder não substituído: {acao} → {template}"

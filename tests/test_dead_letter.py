import pytest
from pathlib import Path

from src.dead_letter import DeadLetterQueue, MAX_TENTATIVAS


@pytest.fixture
def dlq(tmp_path):
    return DeadLetterQueue(db_path=tmp_path / "test_dl.db")


def test_enfileirar_e_listar(dlq):
    dlq.enfileirar("g1", "Grupo 1", "criar_nota", "K2Con", "## Nota", "timeout")
    pendentes = dlq.listar_pendentes()
    assert len(pendentes) == 1
    assert pendentes[0]["acao"] == "criar_nota"
    assert pendentes[0]["projeto"] == "K2Con"
    assert pendentes[0]["tentativas"] == 0


def test_remover_item(dlq):
    item_id = dlq.enfileirar("g1", "Grupo 1", "criar_nota", "K2Con", "conteudo", "erro")
    dlq.remover(item_id)
    assert dlq.total_pendentes() == 0


def test_incrementar_tentativas(dlq):
    item_id = dlq.enfileirar("g1", "Grupo 1", "criar_nota", "K2Con", "conteudo", "erro1")
    dlq.incrementar_tentativas(item_id, "erro2")
    pendentes = dlq.listar_pendentes()
    assert pendentes[0]["tentativas"] == 1
    assert pendentes[0]["ultimo_erro"] == "erro2"


def test_total_pendentes(dlq):
    assert dlq.total_pendentes() == 0
    dlq.enfileirar("g1", "G", "criar_nota", "P1", "c", "e")
    dlq.enfileirar("g1", "G", "criar_task", "P2", "c", "e")
    assert dlq.total_pendentes() == 2


def test_itens_alem_do_limite_nao_aparecem_na_lista(dlq):
    item_id = dlq.enfileirar("g1", "G", "criar_nota", "P", "c", "e")
    for i in range(MAX_TENTATIVAS):
        dlq.incrementar_tentativas(item_id, f"erro {i}")
    assert dlq.total_pendentes() == 0
    assert dlq.listar_pendentes() == []


def test_multiplos_itens_ordenados_por_data(dlq):
    dlq.enfileirar("g1", "G", "criar_nota", "P1", "c", "e")
    dlq.enfileirar("g1", "G", "criar_task", "P2", "c", "e")
    pendentes = dlq.listar_pendentes()
    assert len(pendentes) == 2
    # deve ser ordenado por criado_em ASC
    assert pendentes[0]["acao"] == "criar_nota"

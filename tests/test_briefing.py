"""Testa geração e formatação do briefing matinal."""
import pytest
import respx
import httpx
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.briefing import formatar_briefing_whatsapp, _ler_tasks_pendentes
from src.models import BriefingData, EmailCategoria, EmailClassificado, EmailEntrada


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fazer_email_classificado(resumo="Resumo", urgente=False, categoria=EmailCategoria.INFORMATIVO, codigo=None):
    entrada = EmailEntrada(
        uid="1", remetente="from@test.com", assunto="Assunto",
        corpo="Corpo", data=datetime(2026, 4, 17, 9, 0),
    )
    return EmailClassificado(
        email=entrada, categoria=categoria, resumo=resumo,
        urgente=urgente, codigo_2fa=codigo,
    )


def _fazer_briefing(
    diario=None,
    emails=None,
    tasks=None,
    data="2026-04-17",
):
    return BriefingData(
        data_referencia=data,
        diario=diario or {"data": "2026-04-16", "entradas": 5, "sucesso": 4, "erro": 1, "ambigua": 0, "existe": True},
        emails=emails or [],
        tasks_pendentes=tasks or [],
        gerado_em=datetime(2026, 4, 17, 8, 0),
    )


# ── Formatação ────────────────────────────────────────────────────────────────

def test_briefing_tem_cabecalho():
    briefing = formatar_briefing_whatsapp(_fazer_briefing())
    assert "Briefing Matinal" in briefing
    assert "2026-04-17" in briefing


def test_briefing_diario_com_entradas():
    briefing = formatar_briefing_whatsapp(_fazer_briefing(
        diario={"data": "2026-04-16", "entradas": 5, "sucesso": 4, "erro": 1, "ambigua": 0, "existe": True}
    ))
    assert "5 ações" in briefing
    assert "4 ok" in briefing
    assert "1 erros" in briefing


def test_briefing_diario_sem_entradas():
    briefing = formatar_briefing_whatsapp(_fazer_briefing(
        diario={"data": "2026-04-16", "entradas": 0, "existe": False}
    ))
    assert "Sem registros" in briefing


def test_briefing_diario_sem_erros_emoji_ok():
    briefing = formatar_briefing_whatsapp(_fazer_briefing(
        diario={"data": "2026-04-16", "entradas": 3, "sucesso": 3, "erro": 0, "ambigua": 0, "existe": True}
    ))
    assert "✅" in briefing


def test_briefing_com_tasks():
    tasks = ["[k2con] Revisar proposta", "[gestao-eg] Pagar fatura"]
    briefing = formatar_briefing_whatsapp(_fazer_briefing(tasks=tasks))
    assert "Revisar proposta" in briefing
    assert "Pagar fatura" in briefing


def test_briefing_sem_tasks():
    briefing = formatar_briefing_whatsapp(_fazer_briefing(tasks=[]))
    assert "Nenhuma task pendente" in briefing


def test_briefing_muitas_tasks_trunca():
    tasks = [f"[proj] Task {i}" for i in range(15)]
    briefing = formatar_briefing_whatsapp(_fazer_briefing(tasks=tasks))
    assert "mais 5 tasks" in briefing


def test_briefing_emails_urgentes_destacados():
    emails = [
        _fazer_email_classificado("Fatura $500 vence hoje", urgente=True, categoria=EmailCategoria.INVOICE),
        _fazer_email_classificado("Newsletter semanal", urgente=False),
    ]
    briefing = formatar_briefing_whatsapp(_fazer_briefing(emails=emails))
    assert "urgentes" in briefing.lower()
    assert "Fatura $500" in briefing


def test_briefing_codigo_2fa_exibido():
    emails = [
        _fazer_email_classificado("Código de verificação", urgente=True,
                                   categoria=EmailCategoria.CODIGO_2FA, codigo="847291"),
    ]
    briefing = formatar_briefing_whatsapp(_fazer_briefing(emails=emails))
    assert "847291" in briefing


def test_briefing_sem_emails():
    briefing = formatar_briefing_whatsapp(_fazer_briefing(emails=[]))
    assert "Nenhum e-mail relevante" in briefing


def test_briefing_rodape_eg():
    briefing = formatar_briefing_whatsapp(_fazer_briefing())
    assert "Effective Gain" in briefing


# ── _ler_tasks_pendentes ──────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_ler_tasks_pendentes_retorna_nao_marcadas():
    from src.obsidian import ObsidianClient
    BASE_URL = "http://localhost:27124"

    conteudo_tasks = (
        "# Tasks K2Con\n\n"
        "- [x] Task concluída\n"
        "- [ ] Revisar proposta comercial\n"
        "- [ ] Enviar contrato\n"
    )
    respx.get(f"{BASE_URL}/vault/05 - Tasks/k2con-tasks.md").mock(
        return_value=httpx.Response(200, text=conteudo_tasks)
    )
    # Outros projetos retornam 404
    for proj in ["beef-smash", "rodag", "gestao-eg", "eg-build", "mkt-eg"]:
        respx.get(f"{BASE_URL}/vault/05 - Tasks/{proj}-tasks.md").mock(
            return_value=httpx.Response(404)
        )

    client = ObsidianClient(base_url=BASE_URL, api_key="test")
    tasks = await _ler_tasks_pendentes(client, ["k2con", "beef-smash", "rodag", "gestao-eg", "eg-build", "mkt-eg"])

    assert len(tasks) == 2
    assert any("Revisar proposta" in t for t in tasks)
    assert any("Enviar contrato" in t for t in tasks)
    assert not any("concluída" in t for t in tasks)


@pytest.mark.asyncio
async def test_ler_tasks_pendentes_ignora_erro_obsidian():
    """Falha de conexão em um projeto não deve parar os outros."""
    from src.obsidian import ObsidianClient, ObsidianError
    obsidian = MagicMock(spec=ObsidianClient)
    obsidian.ler_nota = AsyncMock(side_effect=ObsidianError("offline"))

    tasks = await _ler_tasks_pendentes(obsidian, ["k2con"])
    assert tasks == []  # erro silencioso, sem exceção


# ── Scheduler ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_executa_e_envia():
    """BriefingScheduler._executar_briefing deve coletar dados e chamar whatsapp_send_fn."""
    from src.scheduler import BriefingScheduler
    from src.obsidian import ObsidianClient

    obsidian = MagicMock(spec=ObsidianClient)
    obsidian.ler_nota = AsyncMock(return_value="")

    enviados = []

    async def mock_send(numero, texto):
        enviados.append({"numero": numero, "texto": texto})

    scheduler = BriefingScheduler(
        obsidian=obsidian,
        whatsapp_send_fn=mock_send,
        numero_destino="5531999999999",
        hora="08:00",
        email_reader=None,
        anthropic_client=None,
    )

    await scheduler._executar_briefing()

    assert len(enviados) == 1
    assert enviados[0]["numero"] == "5531999999999"
    assert "Briefing Matinal" in enviados[0]["texto"]


@pytest.mark.asyncio
async def test_scheduler_nao_quebra_em_erro():
    """Erro na coleta não deve levantar exceção — scheduler continua rodando."""
    from src.scheduler import BriefingScheduler
    from src.obsidian import ObsidianClient

    obsidian = MagicMock(spec=ObsidianClient)
    obsidian.ler_nota = AsyncMock(side_effect=Exception("conexão perdida"))

    async def mock_send(numero, texto):
        pass

    scheduler = BriefingScheduler(
        obsidian=obsidian,
        whatsapp_send_fn=mock_send,
        numero_destino="5531999999999",
    )

    # Não deve levantar exceção
    await scheduler._executar_briefing()

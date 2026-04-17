"""
Briefing matinal: consolida diário + e-mails + tasks → WhatsApp às 8h.
Nunca pode falhar silenciosamente — registra tudo no diário mesmo em erro.
"""
import logging
from datetime import date, datetime, timedelta

import anthropic

from .email_digest import classificar_emails, formatar_digest_whatsapp
from .email_reader import EmailReader
from .models import BriefingData, EmailClassificado
from .obsidian import ObsidianClient

logger = logging.getLogger(__name__)

TASKS_PROJETOS = list({
    "k2con": "K2Con",
    "beef-smash": "Beef Smash & Co",
    "rodag": "RODAG",
    "gestao-eg": "Gestão EG",
    "eg-build": "EG Build",
    "mkt-eg": "MKT EG",
}.keys())


async def _ler_tasks_pendentes(obsidian: ObsidianClient, projetos: list[str]) -> list[str]:
    """Lê arquivos de tasks de cada projeto e retorna linhas não concluídas."""
    pendentes = []
    for projeto in projetos:
        caminho = f"05 - Tasks/{projeto}-tasks.md"
        try:
            conteudo = await obsidian.ler_nota(caminho)
            for linha in conteudo.splitlines():
                stripped = linha.strip()
                # Markdown checkbox não marcado: "- [ ] texto"
                if stripped.startswith("- [ ]"):
                    pendentes.append(f"[{projeto}] {stripped[6:].strip()}")
        except Exception as e:
            logger.warning("Não foi possível ler tasks de '%s': %s", projeto, e)
    return pendentes


async def coletar_briefing_data(
    obsidian: ObsidianClient,
    email_reader: EmailReader | None,
    anthropic_client: anthropic.Anthropic | None,
) -> BriefingData:
    """
    Coleta todos os dados para o briefing:
    - Métricas do diário de ontem
    - E-mails não lidos classificados (opcional — se email_reader configurado)
    - Tasks pendentes de todos os projetos
    """
    ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    hoje = date.today().strftime("%Y-%m-%d")

    # Diário de ontem
    diario = await obsidian.verificar_diario_hoje.__wrapped__(obsidian) if False else {}
    try:
        from .obsidian import DIARIO_PATH
        conteudo_diario = await obsidian.ler_nota(DIARIO_PATH.format(data=ontem))
        if conteudo_diario:
            linhas = [l for l in conteudo_diario.splitlines() if l.strip().startswith("-")]
            diario = {
                "data": ontem,
                "entradas": len(linhas),
                "sucesso": sum(1 for l in linhas if "✅" in l),
                "erro": sum(1 for l in linhas if "❌" in l),
                "ambigua": sum(1 for l in linhas if "❓" in l),
                "existe": True,
            }
        else:
            diario = {"data": ontem, "entradas": 0, "existe": False}
    except Exception as e:
        logger.warning("Erro ao ler diário de ontem: %s", e)
        diario = {"data": ontem, "entradas": 0, "existe": False}

    # E-mails
    emails_classificados: list[EmailClassificado] = []
    if email_reader and anthropic_client:
        try:
            emails_brutos = email_reader.ler_nao_lidos(limite=20)
            emails_classificados = classificar_emails(anthropic_client, emails_brutos)
        except Exception as e:
            logger.warning("Erro ao ler e-mails para briefing: %s", e)

    # Tasks pendentes
    tasks = await _ler_tasks_pendentes(obsidian, TASKS_PROJETOS)

    return BriefingData(
        data_referencia=hoje,
        diario=diario,
        emails=emails_classificados,
        tasks_pendentes=tasks,
    )


def formatar_briefing_whatsapp(dados: BriefingData) -> str:
    """
    Formata o briefing completo para WhatsApp.
    Estrutura: cabeçalho → diário ontem → tasks pendentes → emails
    """
    linhas = [
        f"☀️ *Briefing Matinal — {dados.data_referencia}*",
        f"_Gerado às {dados.gerado_em.strftime('%H:%M')}_",
        "",
    ]

    # Diário de ontem
    d = dados.diario
    if d.get("existe"):
        status_emoji = "✅" if d.get("erro", 0) == 0 else "⚠️"
        linhas += [
            f"📔 *Diário de ontem ({d['data']})*",
            f"{status_emoji} {d['entradas']} ações | {d['sucesso']} ok | {d['erro']} erros | {d['ambigua']} ambíguas",
            "",
        ]
    else:
        linhas += [f"📔 *Diário de ontem ({d.get('data', 'N/A')})*", "⚪ Sem registros ontem.", ""]

    # Tasks pendentes
    if dados.tasks_pendentes:
        linhas.append(f"📋 *Tasks pendentes ({len(dados.tasks_pendentes)})*")
        for task in dados.tasks_pendentes[:10]:  # máx 10 para não poluir
            linhas.append(f"• {task}")
        if len(dados.tasks_pendentes) > 10:
            linhas.append(f"_...e mais {len(dados.tasks_pendentes) - 10} tasks_")
        linhas.append("")
    else:
        linhas += ["📋 *Tasks pendentes*", "✅ Nenhuma task pendente.", ""]

    # E-mails
    if dados.emails:
        urgentes = [e for e in dados.emails if e.urgente]
        if urgentes:
            linhas.append(f"🔴 *E-mails urgentes ({len(urgentes)})*")
            for em in urgentes[:5]:
                linhas.append(f"• {em.resumo}")
                if em.codigo_2fa:
                    linhas.append(f"  🔑 Código: *{em.codigo_2fa}*")
            linhas.append("")
        outros = [e for e in dados.emails if not e.urgente]
        if outros:
            linhas.append(f"📧 +{len(outros)} e-mails informativos")
    else:
        linhas.append("📧 Nenhum e-mail relevante.")

    linhas.append(f"\n_Integrador EG — Effective Gain_")
    return "\n".join(linhas)

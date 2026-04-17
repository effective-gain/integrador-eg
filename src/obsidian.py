import asyncio
import logging
import re
from datetime import datetime, date

import httpx

from .models import AcaoTipo, ACAO_DESTINO, DiarioEntrada, ObsidianEscrita

logger = logging.getLogger(__name__)

DIARIO_PATH = "06 - Diario/{data}.md"
RETRY_ATTEMPTS = 3
RETRY_DELAY_S = 2.0


class ObsidianError(Exception):
    pass


class DiarioIntegridadeError(Exception):
    """Levantado quando o diário tem gaps ou entradas perdidas."""
    pass


class ObsidianClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "text/markdown",
        }

    def _caminho_para_acao(self, acao: AcaoTipo, projeto: str, data: str) -> str:
        template = ACAO_DESTINO.get(acao, "04 - Inbox/{data}-{projeto}.md")
        # Sanitização: permite apenas alfanuméricos, espaço e hífen — previne path traversal
        projeto_seguro = re.sub(r"[^a-zA-Z0-9À-ÿ \-]", "", projeto)
        projeto_seguro = projeto_seguro.strip().replace(" ", "-") or "Inbox"
        return template.format(data=data, projeto=projeto_seguro)

    async def _executar_com_retry(self, escrita: ObsidianEscrita) -> bool:
        """Tenta escrever até RETRY_ATTEMPTS vezes com backoff exponencial."""
        url = f"{self.base_url}/vault/{escrita.caminho}"
        ultimo_erro: Exception | None = None

        for tentativa in range(1, RETRY_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    if escrita.modo == "create":
                        resp = await client.put(url, content=escrita.conteudo.encode(), headers=self.headers)
                    else:
                        resp = await client.post(url, content=escrita.conteudo.encode(), headers=self.headers)

                    if resp.status_code not in (200, 204):
                        raise ObsidianError(f"Obsidian retornou {resp.status_code}: {resp.text}")

                    if tentativa > 1:
                        logger.warning("Escrita OK na tentativa %d: %s", tentativa, escrita.caminho)
                    return True

            except (httpx.TimeoutException, httpx.ConnectError, ObsidianError) as e:
                ultimo_erro = e
                if tentativa < RETRY_ATTEMPTS:
                    espera = RETRY_DELAY_S * (2 ** (tentativa - 1))
                    logger.warning("Falha %d/%d em %s — aguardando %.1fs: %s",
                                   tentativa, RETRY_ATTEMPTS, escrita.caminho, espera, e)
                    await asyncio.sleep(espera)

        raise ObsidianError(
            f"Falha após {RETRY_ATTEMPTS} tentativas em '{escrita.caminho}': {ultimo_erro}"
        )

    async def criar_ou_append(self, escrita: ObsidianEscrita) -> bool:
        return await self._executar_com_retry(escrita)

    async def ler_nota(self, caminho: str) -> str:
        url = f"{self.base_url}/vault/{caminho}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={**self.headers, "Accept": "text/markdown"})
                if resp.status_code == 404:
                    return ""
                if resp.status_code != 200:
                    raise ObsidianError(f"Erro ao ler nota {caminho}: {resp.status_code}")
                return resp.text
        except httpx.ConnectError:
            raise ObsidianError("Não foi possível conectar ao Obsidian")

    async def registrar_acao(self, acao: AcaoTipo, projeto: str, conteudo: str) -> str:
        data = datetime.now().strftime("%Y-%m-%d")
        caminho = self._caminho_para_acao(acao, projeto, data)
        conteudo_com_header = f"\n\n---\n*Registrado em {datetime.now().strftime('%H:%M')}*\n\n{conteudo}"
        await self.criar_ou_append(ObsidianEscrita(caminho=caminho, conteudo=conteudo_com_header, modo="append"))
        logger.info("Ação registrada: %s → %s", acao, caminho)
        return caminho

    async def registrar_diario(self, entrada: DiarioEntrada) -> None:
        """
        Registra entrada no diário com retry.
        CRÍTICO: nunca pode perder uma entrada — é a fonte de verdade de tudo que foi executado.
        """
        data = entrada.timestamp.strftime("%Y-%m-%d")
        hora = entrada.timestamp.strftime("%H:%M")
        caminho = DIARIO_PATH.format(data=data)

        emoji = "✅" if entrada.resultado == "sucesso" else ("❌" if entrada.resultado == "erro" else "❓")
        linha = (
            f"\n- {hora} {emoji} **{entrada.acao.value}** | {entrada.projeto} | "
            f"{entrada.conteudo_resumo}"
        )
        if entrada.erro_detalhe:
            linha += f" *(erro: {entrada.erro_detalhe})*"

        await self.criar_ou_append(ObsidianEscrita(caminho=caminho, conteudo=linha, modo="append"))
        logger.info("Diário atualizado: %s", caminho)

    async def verificar_diario_hoje(self) -> dict:
        """
        Lê o diário de hoje e retorna métricas de integridade.
        Usado pelo briefing matinal e pelo monitoramento.
        """
        hoje = date.today().strftime("%Y-%m-%d")
        caminho = DIARIO_PATH.format(data=hoje)
        conteudo = await self.ler_nota(caminho)

        if not conteudo:
            return {"data": hoje, "entradas": 0, "sucesso": 0, "erro": 0, "ambigua": 0, "existe": False}

        linhas = [l for l in conteudo.splitlines() if l.strip().startswith("-")]
        return {
            "data": hoje,
            "entradas": len(linhas),
            "sucesso": sum(1 for l in linhas if "✅" in l),
            "erro":    sum(1 for l in linhas if "❌" in l),
            "ambigua": sum(1 for l in linhas if "❓" in l),
            "existe": True,
        }

    async def consultar_tasks(self, projeto: str) -> str:
        """
        Lê o arquivo de tasks do projeto e retorna as pendentes formatadas para WhatsApp.
        Retorna mensagem de 'nenhuma task' se o arquivo não existir ou estiver vazio.
        """
        data = datetime.now().strftime("%Y-%m-%d")
        caminho = self._caminho_para_acao(AcaoTipo.CONSULTAR_TASKS, projeto, data)
        conteudo = await self.ler_nota(caminho)

        if not conteudo:
            return f"📋 Nenhuma task encontrada para *{projeto}*."

        pendentes = [l.strip() for l in conteudo.splitlines() if "- [ ]" in l]
        concluidas = [l for l in conteudo.splitlines() if "- [x]" in l or "- [X]" in l]

        if not pendentes:
            return f"✅ Todas as tasks de *{projeto}* estão concluídas!"

        linhas = [f"📋 *Tasks pendentes — {projeto}*", ""]
        for i, t in enumerate(pendentes, 1):
            texto = t.replace("- [ ]", "").strip()
            linhas.append(f"{i}. {texto}")

        linhas.append(f"\n_{len(pendentes)} pendente(s) · {len(concluidas)} concluída(s)_")
        return "\n".join(linhas)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/",
                    headers={"Authorization": self.headers["Authorization"]},
                )
                return resp.status_code < 500
        except Exception:
            return False

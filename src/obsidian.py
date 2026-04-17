import logging
from datetime import datetime
from pathlib import Path

import httpx

from .models import AcaoTipo, ACAO_DESTINO, DiarioEntrada, ObsidianEscrita

logger = logging.getLogger(__name__)

DIARIO_PATH = "06 - Diario/{data}.md"


class ObsidianError(Exception):
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
        return template.format(
            data=data,
            projeto=projeto.replace(" ", "-").replace("&", "e"),
        )

    async def criar_ou_append(self, escrita: ObsidianEscrita) -> bool:
        url = f"{self.base_url}/vault/{escrita.caminho}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if escrita.modo == "create":
                    resp = await client.put(url, content=escrita.conteudo.encode(), headers=self.headers)
                else:
                    resp = await client.post(url, content=escrita.conteudo.encode(), headers=self.headers)

                if resp.status_code not in (200, 204):
                    raise ObsidianError(f"Obsidian retornou {resp.status_code}: {resp.text}")
                return True

        except httpx.TimeoutException:
            raise ObsidianError("Timeout ao conectar ao Obsidian — verifique se está rodando na porta 27124")
        except httpx.ConnectError:
            raise ObsidianError("Não foi possível conectar ao Obsidian — verifique se está aberto com o plugin REST API ativo")

    async def ler_nota(self, caminho: str) -> str:
        url = f"{self.base_url}/vault/{caminho}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {**self.headers, "Content-Type": "application/json"}
                resp = await client.get(url, headers=headers)
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

        escrita = ObsidianEscrita(
            caminho=caminho,
            conteudo=conteudo_com_header,
            modo="append",
        )
        await self.criar_ou_append(escrita)
        logger.info("Ação registrada: %s → %s", acao, caminho)
        return caminho

    async def registrar_diario(self, entrada: DiarioEntrada) -> None:
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

        escrita = ObsidianEscrita(caminho=caminho, conteudo=linha, modo="append")
        await self.criar_ou_append(escrita)
        logger.info("Diário atualizado: %s", caminho)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/",
                    headers={"Authorization": f"Bearer {self.headers['Authorization'].split()[-1]}"},
                )
                return resp.status_code < 500
        except Exception:
            return False

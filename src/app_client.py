"""
Cliente HTTP para o integrador-eg-app (Next.js).
Notifica o dashboard após cada execução — falhas são silenciosas
para não impactar o fluxo principal do webhook.
"""

import logging
import httpx

from .config import settings

logger = logging.getLogger(__name__)


class AppClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    async def registrar_execucao(
        self,
        grupo_id: str,
        grupo_nome: str,
        acao: str,
        projeto: str,
        resultado: str,
        remetente: str = "",
        conteudo_resumo: str = "",
        erro_detalhe: str = "",
        dna_usado: bool = False,
    ) -> bool:
        """
        Envia a execução para o dashboard (integrador-eg-app).
        Retorna True se sucesso, False se falha (sem exceção).
        """
        if not self.base_url or self.base_url == "http://localhost:3000":
            # Sem URL configurada em produção — skip silencioso
            return False

        payload = {
            "grupo_id": grupo_id,
            "grupo_nome": grupo_nome,
            "remetente": remetente,
            "acao": acao,
            "projeto": projeto,
            "conteudo_resumo": conteudo_resumo[:200] if conteudo_resumo else "",
            "resultado": resultado,
            "erro_detalhe": erro_detalhe or None,
            "dna_usado": dna_usado,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/execucoes",
                    json=payload,
                    headers=self.headers,
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.debug("App client: falha ao registrar execução (não crítico): %s", e)
            return False

    async def registrar_lancamento(
        self,
        descricao: str,
        valor: float,
        tipo: str,
        projeto: str,
        grupo_origem: str = "",
        categoria: str = "",
        fornecedor: str = "",
        data_vencimento: str = "",
    ) -> bool:
        """Cria um lançamento financeiro no dashboard."""
        if not self.base_url:
            return False

        payload = {
            "descricao": descricao,
            "valor": valor,
            "tipo": tipo,
            "projeto": projeto,
            "grupo_origem": grupo_origem,
            "categoria": categoria or None,
            "fornecedor": fornecedor or None,
            "data_vencimento": data_vencimento or None,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/lancamentos",
                    json=payload,
                    headers=self.headers,
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.debug("App client: falha ao registrar lançamento: %s", e)
            return False

    async def registrar_lead(
        self,
        nome: str,
        projeto: str,
        grupo_origem: str = "",
        telefone: str = "",
        notas: str = "",
    ) -> bool:
        """Cria um lead no CRM do dashboard."""
        if not self.base_url:
            return False

        payload = {
            "nome": nome,
            "projeto": projeto,
            "grupo_origem": grupo_origem,
            "telefone": telefone or None,
            "notas": notas or None,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/leads",
                    json=payload,
                    headers=self.headers,
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.debug("App client: falha ao registrar lead: %s", e)
            return False

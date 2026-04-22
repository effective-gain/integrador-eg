"""
Thread persistente por grupo WhatsApp.

Mantém histórico de conversas em memória por grupo_id, no formato correto
para a Anthropic API com tool_use (alternância user/assistant com tool_result).

Diferença do ContextoConversa:
  ContextoConversa — TTL 5min, aguarda resposta de esclarecimento pontual
  HistoricoConversa — TTL 2h, contexto completo de multi-turn para o Claude

O historico é passado diretamente no array `messages` da chamada ao Claude,
permitindo que o classificador entenda referências como "aquele projeto que
discutimos" ou "add mais uma task igual à anterior".
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MAX_PARES = 8       # número máximo de pares user+assistant por grupo
TTL_HORAS = 2       # tempo sem atividade para limpar o histórico


@dataclass
class _HistoricoGrupo:
    mensagens: list[dict] = field(default_factory=list)
    ultima_atividade: datetime = field(default_factory=datetime.now)


class HistoricoConversa:
    """
    Armazena o histórico de mensagens por grupo no formato da Anthropic API.

    Cada interação completa ocupa 3 blocos:
      1. {"role": "user",      "content": "<mensagem original>"}
      2. {"role": "assistant", "content": [tool_use block]}
      3. {"role": "user",      "content": [tool_result block]}

    Ao classificar uma nova mensagem, o array `messages` fica:
      [*historico_anterior, {"role": "user", "content": nova_mensagem}]
    """

    def __init__(self, max_pares: int = MAX_PARES, ttl_horas: int = TTL_HORAS):
        self._store: dict[str, _HistoricoGrupo] = defaultdict(_HistoricoGrupo)
        # 3 blocos por par: user msg + assistant tool_use + user tool_result
        self._max_blocos = max_pares * 3
        self._ttl = timedelta(hours=ttl_horas)

    # ── acesso ─────────────────────────────────────────────────────────────

    def obter(self, grupo_id: str) -> list[dict]:
        """Retorna o histórico do grupo, ou [] se expirado ou vazio."""
        h = self._store[grupo_id]
        if not h.mensagens:
            return []
        if datetime.now() - h.ultima_atividade > self._ttl:
            self.limpar(grupo_id)
            logger.debug("Histórico expirado por TTL | grupo=%s", grupo_id)
            return []
        return list(h.mensagens)

    def total_grupos(self) -> int:
        return len(self._store)

    # ── escrita ────────────────────────────────────────────────────────────

    def adicionar_turno(
        self,
        grupo_id: str,
        mensagem_usuario: str,
        tool_use_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> None:
        """
        Adiciona um turno completo após uma classificação bem-sucedida.
        Registra: mensagem do usuário + tool_use do assistente + tool_result.
        """
        h = self._store[grupo_id]
        h.mensagens.extend([
            # 1. Mensagem do usuário
            {"role": "user", "content": mensagem_usuario},
            # 2. Resposta do assistente (tool call)
            {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": tool_input,
                }],
            },
            # 3. Resultado da ferramenta (sempre ok — já foi processado)
            {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "registrado com sucesso",
                }],
            },
        ])
        h.ultima_atividade = datetime.now()
        self._truncar(grupo_id)

    def limpar(self, grupo_id: str) -> None:
        """Remove o histórico do grupo."""
        if grupo_id in self._store:
            del self._store[grupo_id]

    # ── interno ────────────────────────────────────────────────────────────

    def _truncar(self, grupo_id: str) -> None:
        """Mantém apenas os últimos _max_blocos, sempre em múltiplos de 3."""
        h = self._store[grupo_id]
        if len(h.mensagens) > self._max_blocos:
            # Garante que começa sempre em um bloco "user" (índice múltiplo de 3)
            excesso = len(h.mensagens) - self._max_blocos
            # Arredonda para o próximo múltiplo de 3 para não quebrar a sequência
            excesso = ((excesso + 2) // 3) * 3
            h.mensagens = h.mensagens[excesso:]

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TTL_MINUTOS = 5


@dataclass
class ContextoPendente:
    pergunta: str
    conteudo_original: str
    projeto: str
    criado_em: datetime = field(default_factory=datetime.now)


class ContextoConversa:
    """Cache em memória de contextos de esclarecimento pendentes, com TTL."""

    def __init__(self, ttl_minutos: int = TTL_MINUTOS):
        self._store: dict[tuple[str, str], ContextoPendente] = {}
        self._ttl = timedelta(minutes=ttl_minutos)

    def salvar(self, grupo_id: str, remetente: str, contexto: ContextoPendente) -> None:
        self._store[(grupo_id, remetente)] = contexto
        logger.debug("Contexto salvo para %s/%s", grupo_id, remetente)

    def recuperar(self, grupo_id: str, remetente: str) -> ContextoPendente | None:
        chave = (grupo_id, remetente)
        ctx = self._store.get(chave)
        if ctx is None:
            return None
        if datetime.now() - ctx.criado_em > self._ttl:
            del self._store[chave]
            logger.debug("Contexto expirado para %s/%s", grupo_id, remetente)
            return None
        return ctx

    def limpar(self, grupo_id: str, remetente: str) -> None:
        self._store.pop((grupo_id, remetente), None)

    def total(self) -> int:
        return len(self._store)

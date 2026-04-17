import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/dead_letter.db")
MAX_TENTATIVAS = 5


class DeadLetterQueue:
    """Fila de operações Obsidian que falharam, persistida em SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fila_pendente (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    grupo_id        TEXT NOT NULL,
                    grupo_nome      TEXT NOT NULL,
                    acao            TEXT NOT NULL,
                    projeto         TEXT NOT NULL,
                    conteudo_formatado TEXT NOT NULL,
                    tentativas      INTEGER DEFAULT 0,
                    criado_em       TEXT NOT NULL,
                    ultimo_erro     TEXT
                )
            """)

    def enfileirar(
        self,
        grupo_id: str,
        grupo_nome: str,
        acao: str,
        projeto: str,
        conteudo_formatado: str,
        erro: str,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO fila_pendente
                   (grupo_id, grupo_nome, acao, projeto, conteudo_formatado, criado_em, ultimo_erro)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (grupo_id, grupo_nome, acao, projeto, conteudo_formatado,
                 datetime.now().isoformat(), erro),
            )
            item_id = cur.lastrowid
            logger.warning("Dead letter: enfileirado id=%d | %s → %s", item_id, acao, projeto)
            return item_id

    def listar_pendentes(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM fila_pendente WHERE tentativas < ? ORDER BY criado_em",
                (MAX_TENTATIVAS,),
            ).fetchall()
            return [dict(r) for r in rows]

    def remover(self, item_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM fila_pendente WHERE id = ?", (item_id,))

    def incrementar_tentativas(self, item_id: int, erro: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE fila_pendente SET tentativas = tentativas + 1, ultimo_erro = ? WHERE id = ?",
                (erro, item_id),
            )

    def total_pendentes(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM fila_pendente WHERE tentativas < ?",
                (MAX_TENTATIVAS,),
            ).fetchone()[0]

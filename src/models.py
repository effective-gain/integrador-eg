from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AcaoTipo(str, Enum):
    CRIAR_NOTA = "criar_nota"
    CRIAR_REUNIAO = "criar_reuniao"
    CRIAR_TASK = "criar_task"
    REGISTRAR_DECISAO = "registrar_decisao"
    REGISTRAR_LANCAMENTO = "registrar_lancamento"
    CRIAR_DAILY = "criar_daily"
    ATUALIZAR_STATUS = "atualizar_status"
    CONSULTAR_TASKS = "consultar_tasks"
    AMBIGUA = "ambigua"  # mensagem não tem intenção clara


class Prioridade(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


# Mapeamento de grupo WhatsApp → projeto
GRUPOS_PROJETOS: dict[str, str] = {
    "k2con": "K2Con",
    "beef-smash": "Beef Smash & Co",
    "rodag": "RODAG",
    "gestao-eg": "Gestão EG",
    "eg-build": "EG Build",
    "mkt-eg": "MKT EG",
}

# Mapeamento ação → pasta no Obsidian
ACAO_DESTINO: dict[AcaoTipo, str] = {
    AcaoTipo.CRIAR_NOTA:           "04 - Inbox/{data}-{projeto}.md",
    AcaoTipo.CRIAR_REUNIAO:        "04 - Inbox/Reuniao-{data}-{projeto}.md",
    AcaoTipo.CRIAR_TASK:           "05 - Tasks/{projeto}-tasks.md",
    AcaoTipo.REGISTRAR_DECISAO:    "03 - Decisoes/{data}-{projeto}.md",
    AcaoTipo.REGISTRAR_LANCAMENTO: "04 - Inbox/Lancamento-{data}-{projeto}.md",
    AcaoTipo.CRIAR_DAILY:          "06 - Diario/{data}.md",
    AcaoTipo.ATUALIZAR_STATUS:     "02 - Projetos/{projeto}/status.md",
    AcaoTipo.CONSULTAR_TASKS:      "05 - Tasks/{projeto}-tasks.md",
}

ACAO_EMOJI: dict[AcaoTipo, str] = {
    AcaoTipo.CRIAR_NOTA:           "📝",
    AcaoTipo.CRIAR_REUNIAO:        "📅",
    AcaoTipo.CRIAR_TASK:           "✅",
    AcaoTipo.REGISTRAR_DECISAO:    "🎯",
    AcaoTipo.REGISTRAR_LANCAMENTO: "💰",
    AcaoTipo.CRIAR_DAILY:          "📆",
    AcaoTipo.ATUALIZAR_STATUS:     "🔄",
    AcaoTipo.CONSULTAR_TASKS:      "📋",
}


class MensagemEntrada(BaseModel):
    grupo_id: str = Field(..., description="ID do grupo WhatsApp")
    grupo_nome: str = Field(..., description="Nome do grupo WhatsApp")
    remetente: str = Field(..., description="Número ou nome do remetente")
    conteudo: str = Field(..., description="Texto da mensagem (já transcrito se era áudio)")
    tipo_original: str = Field(default="text", description="text | audio | document | image")
    timestamp: datetime = Field(default_factory=datetime.now)
    arquivo_url: Optional[str] = Field(None, description="URL do arquivo se houver anexo")


class ClassificacaoResult(BaseModel):
    acao: AcaoTipo
    projeto: str = Field(..., description="Nome do projeto mapeado do grupo")
    conteudo_formatado: str = Field(..., description="Conteúdo já formatado para salvar no Obsidian")
    prioridade: Prioridade = Field(default=Prioridade.MEDIA)
    requer_esclarecimento: bool = Field(default=False)
    pergunta_esclarecimento: Optional[str] = Field(None, description="Pergunta a fazer se ambígua")
    resumo_confirmacao: str = Field(..., description="Mensagem de confirmação para enviar ao cliente")
    idioma_detectado: str = Field(default="pt", description="pt | es | en")


class ObsidianEscrita(BaseModel):
    caminho: str
    conteudo: str
    modo: str = Field(default="append", description="append | create")


class DiarioEntrada(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    grupo: str
    projeto: str
    acao: AcaoTipo
    conteudo_resumo: str
    resultado: str = Field(default="sucesso", description="sucesso | erro | ambigua")
    erro_detalhe: Optional[str] = None

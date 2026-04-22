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
    ENVIAR_EMAIL = "enviar_email"
    RESPONDER_EMAIL = "responder_email"
    ENCAMINHAR_EMAIL = "encaminhar_email"
    CRIAR_RASCUNHO = "criar_rascunho"
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
    AcaoTipo.ENVIAR_EMAIL:         "04 - Inbox/Email-{data}-{projeto}.md",
    AcaoTipo.RESPONDER_EMAIL:      "04 - Inbox/Email-{data}-{projeto}.md",
    AcaoTipo.ENCAMINHAR_EMAIL:     "04 - Inbox/Email-{data}-{projeto}.md",
    AcaoTipo.CRIAR_RASCUNHO:       "04 - Inbox/Rascunho-{data}-{projeto}.md",
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
    AcaoTipo.ENVIAR_EMAIL:         "📧",
    AcaoTipo.RESPONDER_EMAIL:      "↩️",
    AcaoTipo.ENCAMINHAR_EMAIL:     "↪️",
    AcaoTipo.CRIAR_RASCUNHO:       "✉️",
    AcaoTipo.AMBIGUA:              "❓",
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

    # Metadados do tool call (preenchidos pelo Classifier com tool use)
    tool_use_id: Optional[str] = Field(None, description="ID do tool_use retornado pela API")
    tool_name: Optional[str] = Field(None, description="Nome da ferramenta chamada pelo Claude")
    tool_input: Optional[dict] = Field(None, description="Input completo do tool call")

    # Campos extras para registrar_lancamento
    lancamento_valor: Optional[float] = Field(None, description="Valor do lançamento financeiro")
    lancamento_tipo: Optional[str] = Field(None, description="receita | despesa")
    lancamento_categoria: Optional[str] = Field(None)
    lancamento_fornecedor: Optional[str] = Field(None)
    lancamento_data_vencimento: Optional[str] = Field(None, description="YYYY-MM-DD")

    # Campos específicos para ações de e-mail
    email_para: Optional[str] = Field(None, description="Destinatário(s) — ex: cliente@empresa.com")
    email_assunto: Optional[str] = Field(None, description="Assunto do e-mail")
    email_corpo: Optional[str] = Field(None, description="Corpo completo do e-mail, pronto para envio")
    email_tipo: Optional[str] = Field(None, description="invoice | pergunta | proposta | follow_up | personalizado")
    email_message_id: Optional[str] = Field(None, description="ID da mensagem original (para responder/encaminhar)")
    email_cc: Optional[str] = Field(None, description="CC do e-mail, separado por vírgulas")
    email_bcc: Optional[str] = Field(None, description="BCC do e-mail, separado por vírgulas")


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


class EmailCategoria(str, Enum):
    INVOICE = "invoice"
    TASK = "task"
    CODIGO_2FA = "codigo_2fa"
    INFORMATIVO = "informativo"
    SPAM = "spam"


class EmailEntrada(BaseModel):
    uid: str
    remetente: str
    assunto: str
    corpo: str
    data: datetime
    tem_anexo: bool = False


class EmailClassificado(BaseModel):
    email: EmailEntrada
    categoria: EmailCategoria
    resumo: str
    urgente: bool = False
    codigo_2fa: Optional[str] = None
    acao_sugerida: Optional[str] = None


class BriefingData(BaseModel):
    data_referencia: str = Field(..., description="Data do briefing, ex: 2026-04-17")
    diario: dict = Field(default_factory=dict, description="Métricas do diário do dia anterior")
    emails: list[EmailClassificado] = Field(default_factory=list)
    tasks_pendentes: list[str] = Field(default_factory=list, description="Linhas de tasks pendentes por projeto")
    gerado_em: datetime = Field(default_factory=datetime.now)

"""
Classificador de intenções do Integrador EG.

Usa a Anthropic API com *tool use* nativo — o Claude chama a ferramenta
correspondente à ação detectada em vez de retornar JSON que precisaria ser
parseado. Isso elimina falhas de parsing e torna o sistema mais robusto.

Padrão de caching (EG OS):
  Bloco 1 — Instruções estáticas (CACHED, ephemeral)
  Bloco 2 — DNA narrativo do projeto (CACHED quando presente)

Historico multi-turn:
  O array messages pode conter turnos anteriores do grupo (via HistoricoConversa),
  dando ao Claude contexto sobre mensagens recentes sem precisar repetir o projeto.
"""

import logging
from pathlib import Path

import anthropic

from .models import (
    AcaoTipo,
    ClassificacaoResult,
    MensagemEntrada,
    Prioridade,
    GRUPOS_PROJETOS,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classifier_system.md"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024  # tool calls precisam de mais tokens que plain JSON


# ── Definição das ferramentas ──────────────────────────────────────────────────

def _base_schema(extras: dict | None = None) -> dict:
    """Schema base compartilhado pela maioria das ações."""
    props = {
        "projeto": {
            "type": "string",
            "description": "Nome do projeto conforme mapeado do grupo WhatsApp",
        },
        "conteudo_formatado": {
            "type": "string",
            "description": "Conteúdo em Markdown limpo pronto para salvar no Obsidian. "
                           "Use ## Título, listas com -, negritos com **. "
                           "Inclua data e remetente no cabeçalho.",
        },
        "resumo_confirmacao": {
            "type": "string",
            "description": "Frase curta de confirmação no idioma da mensagem. Ex: 'Nota criada para K2Con 📝'",
        },
        "prioridade": {
            "type": "string",
            "enum": ["alta", "media", "baixa"],
            "description": "Prioridade inferida da mensagem",
        },
        "idioma_detectado": {
            "type": "string",
            "enum": ["pt", "es", "en"],
            "description": "Idioma da mensagem original",
        },
    }
    if extras:
        props.update(extras)
    return {
        "type": "object",
        "properties": props,
        "required": ["projeto", "conteudo_formatado", "resumo_confirmacao"],
    }


TOOLS: list[dict] = [
    {
        "name": "criar_nota",
        "description": "Registra uma nota, observação ou informação genérica no Obsidian.",
        "input_schema": _base_schema(),
    },
    {
        "name": "criar_reuniao",
        "description": "Registra uma reunião — deve ter ao menos data, hora ou pauta identificável.",
        "input_schema": _base_schema(),
    },
    {
        "name": "criar_task",
        "description": "Cria uma tarefa a ser executada, com ou sem prazo e responsável.",
        "input_schema": _base_schema(),
    },
    {
        "name": "registrar_decisao",
        "description": "Documenta uma decisão tomada pela equipe.",
        "input_schema": _base_schema(),
    },
    {
        "name": "atualizar_status",
        "description": "Atualiza o status de um projeto ou tarefa já existente.",
        "input_schema": _base_schema(),
    },
    {
        "name": "criar_daily",
        "description": "Registra o diário do dia com atualizações gerais de progresso.",
        "input_schema": _base_schema(),
    },
    {
        "name": "consultar_tasks",
        "description": "Consulta as tarefas pendentes do projeto. NÃO escreve nada — apenas lê.",
        "input_schema": {
            "type": "object",
            "properties": {
                "projeto": {
                    "type": "string",
                    "description": "Nome do projeto a consultar",
                },
                "resumo_confirmacao": {
                    "type": "string",
                    "description": "Mensagem de confirmação breve, ex: 'Consultando tasks de K2Con...'",
                },
            },
            "required": ["projeto", "resumo_confirmacao"],
        },
    },
    {
        "name": "registrar_lancamento",
        "description": "Registra um lançamento financeiro (valor, tipo, fornecedor, categoria).",
        "input_schema": _base_schema({
            "valor": {
                "type": "number",
                "description": "Valor numérico do lançamento (ex: 1500.00)",
            },
            "tipo": {
                "type": "string",
                "enum": ["receita", "despesa"],
                "description": "Se é entrada ou saída de dinheiro",
            },
            "categoria": {
                "type": "string",
                "description": "Categoria do lançamento (ex: fornecedor, marketing, operacional)",
            },
            "fornecedor": {
                "type": "string",
                "description": "Nome do fornecedor ou cliente, se mencionado",
            },
            "data_vencimento": {
                "type": "string",
                "description": "Data de vencimento no formato YYYY-MM-DD, se mencionada",
            },
        }),
    },
    {
        "name": "enviar_email",
        "description": "Redige e envia um novo e-mail para um ou mais destinatários.",
        "input_schema": _base_schema({
            "email_para": {
                "type": "string",
                "description": "Destinatário(s) — ex: cliente@empresa.com",
            },
            "email_assunto": {
                "type": "string",
                "description": "Assunto do e-mail",
            },
            "email_corpo": {
                "type": "string",
                "description": "Corpo completo do e-mail, pronto para envio",
            },
            "email_tipo": {
                "type": "string",
                "enum": ["invoice", "pergunta", "proposta", "follow_up", "personalizado"],
                "description": "Tipo/categoria do e-mail",
            },
            "email_cc": {
                "type": "string",
                "description": "CC separado por vírgulas (opcional)",
            },
            "email_bcc": {
                "type": "string",
                "description": "BCC separado por vírgulas (opcional)",
            },
        }),
    },
    {
        "name": "responder_email",
        "description": "Responde a um e-mail recebido. Requer referência ao e-mail original.",
        "input_schema": _base_schema({
            "email_para": {
                "type": "string",
                "description": "Destinatário (normalmente quem enviou o e-mail original)",
            },
            "email_assunto": {
                "type": "string",
                "description": "Assunto com Re: prefixado",
            },
            "email_corpo": {
                "type": "string",
                "description": "Corpo da resposta",
            },
            "email_message_id": {
                "type": "string",
                "description": "ID do e-mail original para threading (se conhecido)",
            },
            "email_cc": {
                "type": "string",
                "description": "CC separado por vírgulas (opcional)",
            },
        }),
    },
    {
        "name": "encaminhar_email",
        "description": "Encaminha um e-mail existente para outro destinatário.",
        "input_schema": _base_schema({
            "email_para": {
                "type": "string",
                "description": "Novo destinatário para encaminhar",
            },
            "email_assunto": {
                "type": "string",
                "description": "Assunto com Fwd: prefixado",
            },
            "email_corpo": {
                "type": "string",
                "description": "Corpo com conteúdo encaminhado e comentário adicional",
            },
            "email_message_id": {
                "type": "string",
                "description": "ID do e-mail original (se conhecido)",
            },
        }),
    },
    {
        "name": "criar_rascunho",
        "description": "Salva um rascunho de e-mail no Obsidian sem enviar.",
        "input_schema": _base_schema({
            "email_para": {
                "type": "string",
                "description": "Destinatário pretendido",
            },
            "email_assunto": {
                "type": "string",
                "description": "Assunto do rascunho",
            },
            "email_corpo": {
                "type": "string",
                "description": "Corpo do rascunho",
            },
            "email_tipo": {
                "type": "string",
                "enum": ["invoice", "pergunta", "proposta", "follow_up", "personalizado"],
                "description": "Tipo/categoria do e-mail",
            },
        }),
    },
    {
        "name": "pedir_esclarecimento",
        "description": (
            "Use quando a mensagem for ambígua, faltar dados essenciais, ou "
            "quando não for possível agir com segurança sem mais informação. "
            "Exemplos: 'reunião' sem data/hora/pauta, projeto não identificável, "
            "mensagem que poderia ser duas ações diferentes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "projeto": {
                    "type": "string",
                    "description": "Projeto inferido, ou 'desconhecido' se não identificável",
                },
                "pergunta": {
                    "type": "string",
                    "description": "Pergunta clara e objetiva para o usuário, no idioma da mensagem",
                },
            },
            "required": ["projeto", "pergunta"],
        },
    },
]

# Mapeamento: nome da tool → AcaoTipo
_TOOL_PARA_ACAO: dict[str, AcaoTipo] = {
    "criar_nota":           AcaoTipo.CRIAR_NOTA,
    "criar_reuniao":        AcaoTipo.CRIAR_REUNIAO,
    "criar_task":           AcaoTipo.CRIAR_TASK,
    "registrar_decisao":    AcaoTipo.REGISTRAR_DECISAO,
    "atualizar_status":     AcaoTipo.ATUALIZAR_STATUS,
    "criar_daily":          AcaoTipo.CRIAR_DAILY,
    "consultar_tasks":      AcaoTipo.CONSULTAR_TASKS,
    "registrar_lancamento": AcaoTipo.REGISTRAR_LANCAMENTO,
    "enviar_email":         AcaoTipo.ENVIAR_EMAIL,
    "responder_email":      AcaoTipo.RESPONDER_EMAIL,
    "encaminhar_email":     AcaoTipo.ENCAMINHAR_EMAIL,
    "criar_rascunho":       AcaoTipo.CRIAR_RASCUNHO,
    "pedir_esclarecimento": AcaoTipo.AMBIGUA,
}

# Ferramentas de e-mail — extraem campos email_* do tool_input
_EMAIL_TOOLS = {"enviar_email", "responder_email", "encaminhar_email", "criar_rascunho"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _projeto_do_grupo(grupo_nome: str) -> str:
    nome_lower = grupo_nome.lower()
    for chave, projeto in GRUPOS_PROJETOS.items():
        if chave in nome_lower:
            return projeto
    return grupo_nome


def _montar_system_blocks(dna_projeto: str) -> list[dict]:
    """
    Blocos de system com cache_control (padrão EG OS):
      Bloco 1 — Instruções estáticas (CACHED)
      Bloco 2 — DNA narrativo do projeto (CACHED quando presente)
    """
    instrucoes = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    blocos: list[dict] = [
        {
            "type": "text",
            "text": instrucoes,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if dna_projeto.strip():
        blocos.append({
            "type": "text",
            "text": f"## DNA DO PROJETO\n\n{dna_projeto}",
            "cache_control": {"type": "ephemeral"},
        })
    return blocos


def _montar_user_message(mensagem: MensagemEntrada, projeto: str) -> str:
    return (
        f"**Grupo:** {mensagem.grupo_nome}\n"
        f"**Projeto:** {projeto}\n"
        f"**Remetente:** {mensagem.remetente}\n"
        f"**Data/Hora:** {mensagem.timestamp.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"**Mensagem:**\n{mensagem.conteudo}"
    )


def _resultado_de_tool(tool_name: str, tool_input: dict, tool_use_id: str, projeto: str) -> ClassificacaoResult:
    """Converte o tool call do Claude em ClassificacaoResult."""
    acao = _TOOL_PARA_ACAO.get(tool_name, AcaoTipo.AMBIGUA)

    if tool_name == "pedir_esclarecimento":
        pergunta = tool_input.get("pergunta", "Pode detalhar melhor?")
        return ClassificacaoResult(
            acao=AcaoTipo.AMBIGUA,
            projeto=tool_input.get("projeto", projeto),
            conteudo_formatado="",
            requer_esclarecimento=True,
            pergunta_esclarecimento=pergunta,
            resumo_confirmacao=pergunta,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    if tool_name == "consultar_tasks":
        return ClassificacaoResult(
            acao=AcaoTipo.CONSULTAR_TASKS,
            projeto=tool_input.get("projeto", projeto),
            conteudo_formatado="",
            resumo_confirmacao=tool_input.get("resumo_confirmacao", "Consultando tasks..."),
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    # Campos de e-mail — presentes apenas nas ferramentas de e-mail
    email_kwargs: dict = {}
    if tool_name in _EMAIL_TOOLS:
        email_kwargs = {
            "email_para":       tool_input.get("email_para"),
            "email_assunto":    tool_input.get("email_assunto"),
            "email_corpo":      tool_input.get("email_corpo"),
            "email_tipo":       tool_input.get("email_tipo"),
            "email_message_id": tool_input.get("email_message_id"),
            "email_cc":         tool_input.get("email_cc"),
            "email_bcc":        tool_input.get("email_bcc"),
        }

    return ClassificacaoResult(
        acao=acao,
        projeto=tool_input.get("projeto", projeto),
        conteudo_formatado=tool_input.get("conteudo_formatado", ""),
        prioridade=Prioridade(tool_input.get("prioridade", "media")),
        resumo_confirmacao=tool_input.get("resumo_confirmacao", "Registrado ✅"),
        idioma_detectado=tool_input.get("idioma_detectado", "pt"),
        # campos extras para lançamento financeiro
        lancamento_valor=tool_input.get("valor"),
        lancamento_tipo=tool_input.get("tipo"),
        lancamento_categoria=tool_input.get("categoria"),
        lancamento_fornecedor=tool_input.get("fornecedor"),
        lancamento_data_vencimento=tool_input.get("data_vencimento"),
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        tool_input=tool_input,
        **email_kwargs,
    )


# ── Classifier ────────────────────────────────────────────────────────────────

class Classifier:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def classificar(
        self,
        mensagem: MensagemEntrada,
        dna_projeto: str = "",
        historico: list[dict] | None = None,
    ) -> ClassificacaoResult:
        """
        Classifica a mensagem usando tool use nativo da Anthropic API.

        Args:
            mensagem:   Mensagem recebida do WhatsApp
            dna_projeto: Conteúdo do DNA narrativo do projeto (opcional, cached)
            historico:  Turnos anteriores do grupo para contexto multi-turn (opcional)

        Returns:
            ClassificacaoResult com a ação, projeto, conteúdo e metadados do tool call
        """
        projeto = _projeto_do_grupo(mensagem.grupo_nome)
        system_blocks = _montar_system_blocks(dna_projeto)
        user_message = _montar_user_message(mensagem, projeto)

        # Monta o array de messages: histórico anterior + mensagem atual
        messages: list[dict] = [*(historico or []), {"role": "user", "content": user_message}]

        com_dna = bool(dna_projeto.strip())
        com_hist = len(historico or []) // 3  # número de turnos anteriores
        logger.info(
            "Classificando | grupo='%s' projeto='%s' dna=%s historico=%d turnos",
            mensagem.grupo_nome, projeto, "sim" if com_dna else "não", com_hist,
        )

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_blocks,
                tools=TOOLS,
                tool_choice={"type": "any"},  # força sempre um tool call
                messages=messages,
            )

            # Extrai o tool call da resposta
            tool_block = next(
                (b for b in response.content if b.type == "tool_use"),
                None,
            )

            if tool_block is None:
                logger.warning("Nenhum tool call retornado — usando fallback")
                return ClassificacaoResult(
                    acao=AcaoTipo.AMBIGUA,
                    projeto=projeto,
                    conteudo_formatado="",
                    requer_esclarecimento=True,
                    pergunta_esclarecimento="Não entendi bem. Pode detalhar?",
                    resumo_confirmacao="Não entendi bem. Pode detalhar?",
                )

            resultado = _resultado_de_tool(
                tool_name=tool_block.name,
                tool_input=tool_block.input,
                tool_use_id=tool_block.id,
                projeto=projeto,
            )

            logger.info(
                "Classificação: acao=%s projeto=%s requer_esclarecimento=%s idioma=%s",
                resultado.acao, resultado.projeto,
                resultado.requer_esclarecimento, resultado.idioma_detectado,
            )
            return resultado

        except anthropic.APIError as e:
            logger.error("Erro na API Anthropic: %s", e)
            raise

# Integrador EG — Visão Geral e Arquitetura

**Versão:** Abril 2026 | **Testes:** 184 passando | **Status:** Ativo em desenvolvimento

---

## O que é o Integrador EG

O Integrador EG é a camada central de integração da Effective Gain. Ele conecta mensagens de WhatsApp à inteligência do Claude (Anthropic) e executa ações automatizadas em sistemas externos — principalmente o Obsidian (vault local), portais financeiros e e-mail.

Não é apenas uma API. É o ponto onde decisões de roteamento acontecem, onde dados de fontes diferentes se encontram, e onde a lógica de negócio da EG vira código executável.

**Analogia:** o EG OS orquestra agentes e define o que fazer. O Integrador EG é o encanamento que faz o dado chegar no lugar certo, na hora certa, no formato certo.

---

## Fluxo completo do sistema

```
Mensagem WhatsApp (texto ou áudio)
        ↓
Evolution API (webhook POST)
        ↓
FastAPI /webhook/whatsapp
        ↓
1. Detecta se é comando de bot (/pausar, /ativar, /status)
2. Verifica se bot está ativo no grupo
3. Transcreve áudio → Whisper (se for áudio)
4. Lê DNA do projeto no Obsidian (contexto)
5. Carrega histórico da conversa (últimos 8 turnos)
6. Claude Sonnet 4.6 classifica via tool_use nativo
7. Obsidian REST API executa a ação
8. Registra no diário do Obsidian
9. Registra no histórico multi-turn
10. (opcional) Envia confirmação de volta ao WhatsApp
```

---

## Componentes e responsabilidades

### Evolution API
- Captura mensagens dos grupos de WhatsApp
- Envia webhook POST para o FastAPI do Integrador
- Suporta: texto, áudio, imagem, documento
- Número: +55 31 97224-4045 (Luiz/EG)
- **Modo de uso:** passivo — o bot só RECEBE mensagens. Não precisa enviar resposta de volta (opcional).

### FastAPI (api/webhook.py)
- Endpoint principal: `POST /webhook/whatsapp`
- Endpoint de saúde: `GET /health`
- Gerencia todo o fluxo: parse → transcrição → classificação → execução → diário
- Autenticação via `x-api-key` header (WEBHOOK_SECRET no .env)

### Claude Sonnet 4.6 (src/classifier.py)
- Classifica a intenção da mensagem usando **tool_use nativo** (não JSON parseado)
- O Claude chama a ferramenta correspondente à ação detectada
- 13 ferramentas disponíveis: criar_nota, criar_reuniao, criar_task, registrar_decisao, atualizar_status, criar_daily, consultar_tasks, registrar_lancamento, enviar_email, responder_email, encaminhar_email, criar_rascunho, pedir_esclarecimento
- Usa prompt caching (ephemeral) para reduzir custo e latência

### Obsidian REST API (src/obsidian.py)
- Vault local em `C:\Users\user\Documents\Effective Gain`
- Porta 27124, HTTPS local
- Operações: ler arquivo, criar arquivo, append em arquivo
- Retry com backoff exponencial (3 tentativas)

### OpenAI Whisper (src/transcriber.py)
- Transcreve áudios do WhatsApp para texto
- Idioma: pt-BR por padrão
- Fallback claro quando não configurado

### BotStatus (src/bot_status.py)
- Controla se o bot está ativo ou pausado por grupo
- Persistido em Postgres (asyncpg)
- Comandos: /pausar, /pausar 2h, /pausar 30m, /ativar, /status
- TTL automático: se pausado por tempo definido, reativa sozinho

### HistoricoConversa (src/historico.py)
- Armazena histórico de conversas em memória por grupo
- TTL: 2 horas de inatividade
- Máximo: 8 pares de turnos por grupo
- Formato correto para Anthropic API multi-turn com tool_use

### DeadLetterQueue (src/dead_letter.py)
- Armazena ações que falharam para reprocessamento
- Persistido em Postgres (asyncpg)
- Máximo 5 tentativas por item

---

## Mapeamento de grupos WhatsApp → Projetos

| Grupo WhatsApp (substring) | Projeto no sistema |
|----------------------------|--------------------|
| k2con | K2Con |
| beef-smash | Beef Smash & Co |
| rodag | RODAG |
| gestao-eg | Gestão EG |
| eg-build | EG Build |
| mkt-eg | MKT EG |

O mapeamento é feito pelo `grupo_nome` recebido no webhook. O sistema identifica o projeto automaticamente sem configuração por mensagem.

---

## Ações suportadas

| Ação | Emoji | Destino no Obsidian |
|------|-------|---------------------|
| criar_nota | 📝 | 04 - Inbox/{data}-{projeto}.md |
| criar_reuniao | 📅 | 04 - Inbox/Reuniao-{data}-{projeto}.md |
| criar_task | ✅ | 05 - Tasks/{projeto}-tasks.md |
| registrar_decisao | 🎯 | 03 - Decisoes/{data}-{projeto}.md |
| registrar_lancamento | 💰 | 04 - Inbox/Lancamento-{data}-{projeto}.md |
| criar_daily | 📆 | 06 - Diario/{data}.md |
| atualizar_status | 🔄 | 02 - Projetos/{projeto}/status.md |
| consultar_tasks | 📋 | 05 - Tasks/{projeto}-tasks.md |
| enviar_email | 📧 | 04 - Inbox/Email-{data}-{projeto}.md |
| responder_email | ↩️ | 04 - Inbox/Email-{data}-{projeto}.md |
| encaminhar_email | ↪️ | 04 - Inbox/Email-{data}-{projeto}.md |
| criar_rascunho | ✉️ | 04 - Inbox/Rascunho-{data}-{projeto}.md |
| ambigua | ❓ | — (pede esclarecimento) |

---

## Stack tecnológico

| Camada | Tecnologia | Versão/Detalhe |
|--------|-----------|----------------|
| API | FastAPI + Pydantic v2 | Python 3.12 |
| AI | Claude Sonnet 4.6 (Anthropic) | tool_use nativo |
| Transcrição | OpenAI Whisper | pt-BR |
| WhatsApp | Evolution API | Webhook passivo |
| Knowledge Base | Obsidian REST API | Porta 27124, local |
| Banco | Postgres (asyncpg) | Dead Letter + BotStatus |
| Testes | pytest + pytest-asyncio | 184 testes |
| Deploy | Easypanel (Hostinger) | Docker container |

---

## Variáveis de ambiente (.env)

```env
ANTHROPIC_API_KEY       # Claude API
OPENAI_API_KEY          # Whisper
OBSIDIAN_API_KEY        # Obsidian REST API
EVOLUTION_API_URL       # URL da Evolution API
EVOLUTION_INSTANCE      # Nome da instância WhatsApp
EVOLUTION_API_KEY       # Chave Evolution API
WEBHOOK_SECRET          # Autenticação do webhook (x-api-key)
DATABASE_URL            # Postgres para DLQ e BotStatus
```

---

## Estrutura do repositório

```
integrador-eg/
├── api/
│   └── webhook.py          ← FastAPI: /health + /webhook/whatsapp
├── src/
│   ├── models.py            ← tipos Pydantic (AcaoTipo, ClassificacaoResult, etc.)
│   ├── classifier.py        ← Claude Sonnet 4.6 + tool_use nativo
│   ├── obsidian.py          ← REST API + retry + diário
│   ├── whatsapp.py          ← Evolution API (recv + send)
│   ├── transcriber.py       ← OpenAI Whisper
│   ├── bot_status.py        ← on/off por grupo (Postgres async)
│   ├── historico.py         ← histórico multi-turn em memória
│   ├── dead_letter.py       ← fila de falhas (Postgres async)
│   ├── email_reader.py      ← IMAP4_SSL Gmail
│   ├── email_digest.py      ← Claude Haiku classifica emails
│   ├── briefing.py          ← briefing matinal consolidado
│   ├── scheduler.py         ← APScheduler asyncio
│   ├── receita.py           ← engine YAML→Playwright
│   ├── configuracoes.py     ← configs dinâmicas no Postgres
│   └── config.py            ← pydantic-settings (.env)
├── prompts/
│   └── classifier_system.md ← prompt do classificador
├── docs/                    ← base de conhecimento (NotebookLM)
├── tests/                   ← 184 testes, todos passando
├── pytest.ini               ← asyncio_mode = auto
└── .env.example
```

---

## Princípios de design

1. **Grupo WhatsApp como contexto** — o grupo define o projeto automaticamente, sem ambiguidade
2. **Tool use nativo** — Claude chama ferramentas diretamente, sem parsing de JSON frágil
3. **Prompt caching** — instruções estáticas e DNA do projeto cacheados para reduzir custo
4. **Multi-turn** — histórico de conversa preservado por grupo para referências ("aquela task", "o projeto que falamos")
5. **Async first** — todo I/O é async; SQLite síncrono foi migrado para Postgres asyncpg
6. **Dead letter** — falhas não se perdem; vão para fila de reprocessamento
7. **Modo passivo** — bot recebe mensagens e age, sem necessidade de responder de volta

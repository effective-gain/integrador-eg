# Integrador EG

**Effective Gain — Camada Central de Integração**
**Status:** ✅ 184 testes passando | ⏳ Deploy pendente | 📱 Evolution API a configurar

---

## O que é

O Integrador EG é a interface mobile do EG OS via WhatsApp. Transforma mensagens de texto ou áudio enviadas em grupos de WhatsApp por projeto em ações executadas automaticamente no Obsidian — via Claude Sonnet 4.6 com tool_use nativo.

Não é só uma API. É o encanamento que faz cada mensagem virar ação rastreável: nota, task, decisão, lançamento financeiro, e-mail — tudo no lugar certo, com contexto do projeto, sem abrir nenhum sistema.

---

## Fluxo completo

```
Mensagem WhatsApp (texto ou áudio)
        ↓
Evolution API — webhook POST
        ↓
FastAPI /webhook/whatsapp
        ↓
1. Detecta comando de bot (/pausar, /ativar, /status)
2. Verifica se bot está ativo no grupo
3. Transcreve áudio → OpenAI Whisper (se áudio)
4. Lê DNA do projeto no Obsidian (contexto rico para o Claude)
5. Carrega histórico da conversa (últimos 8 turnos, TTL 2h)
6. Claude Sonnet 4.6 classifica via tool_use nativo (13 ferramentas)
7. Obsidian REST API executa a ação no vault
8. Registra no diário do Obsidian
9. Atualiza histórico multi-turn do grupo
```

---

## Grupos WhatsApp → Projetos

| Grupo | Projeto | DNA Obsidian | NotebookLM |
|-------|---------|--------------|------------|
| `k2con` | K2Con | `01 - Projetos/K2Con.md` | `72edea74` |
| `beef-smash` | EG Food (Beef Smash & Co) | `01 - Projetos/EG Food.md` | `d5eb240a` |
| `rodag` | RODAG | `01 - Projetos/RODAG.md` | `3cf62a11` |
| `gestao-eg` | Gestão EG | `01 - Projetos/Gestao EG.md` | `06d696cd` |
| `eg-build` | EG Build OS | `01 - Projetos/EG Build OS.md` | `2a5a0210` |
| `mkt-eg` | MKT EG | `01 - Projetos/MKT EG.md` | `0ebd3fd5` |

> **Grupos ainda não criados.** Número +55 31 97224-4045 precisa ser conectado à Evolution API primeiro.

---

## Ações suportadas (13 ferramentas no Claude)

| Ação | Emoji | Destino Obsidian | Grupos |
|------|-------|-----------------|--------|
| `criar_nota` | 📝 | `04 - Inbox/{data}-{projeto}.md` | Todos |
| `criar_reuniao` | 📅 | `04 - Inbox/Reuniao-{data}.md` | Todos |
| `criar_task` | ✅ | `05 - Tasks/{projeto}-tasks.md` | Todos |
| `registrar_decisao` | 🎯 | `03 - Decisoes/{data}-{projeto}.md` | Todos |
| `registrar_lancamento` | 💰 | `04 - Inbox/Lancamento-{data}.md` | Financeiros |
| `criar_daily` | 📆 | `06 - Diario/{data}.md` | Todos |
| `atualizar_status` | 🔄 | `02 - Projetos/{projeto}/status.md` | Todos |
| `consultar_tasks` | 📋 | leitura `05 - Tasks/` | Todos |
| `enviar_email` | 📧 | `04 - Inbox/Email-{data}.md` | Todos |
| `responder_email` | ↩️ | `04 - Inbox/Email-{data}.md` | Todos |
| `encaminhar_email` | ↪️ | `04 - Inbox/Email-{data}.md` | Todos |
| `criar_rascunho` | ✉️ | `04 - Inbox/Rascunho-{data}.md` | Todos |
| `pedir_esclarecimento` | ❓ | — (aguarda resposta) | Todos |

---

## Por que tool_use nativo (não JSON)

Na versão anterior, Claude retornava JSON em texto que o sistema parseava. Isso causava falhas quando Claude adicionava texto extra, ou campos com nomes errados.

Com **Anthropic tool_use nativo**, Claude chama diretamente a ferramenta correspondente — preenchendo campos estruturados. A API garante o tipo de cada campo. Sem JSON para parsear, sem falhas silenciosas.

**Resultado:** classificação 100% confiável com `tool_choice: {"type": "any"}`.

---

## Controle do bot por grupo

```
/pausar          → pausa indefinidamente
/pausar 2h       → pausa por 2 horas
/pausar 30m      → pausa por 30 minutos
/pausar 1h30m    → pausa por 1h30
/ativar          → reativa
/status          → mostra estado atual
```

Estado persiste em Postgres — sobrevive a restarts do servidor. Auto-reativação quando TTL expira.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| API | FastAPI + Pydantic v2 (Python 3.12) |
| AI | Claude Sonnet 4.6 — tool_use nativo |
| Transcrição | OpenAI Whisper (pt-BR) |
| WhatsApp | Evolution API — webhook passivo |
| Knowledge Base | Obsidian REST API porta 27124 |
| Banco | Postgres async (asyncpg) — DLQ + BotStatus |
| Deploy | Easypanel (Hostinger) |
| Testes | pytest + pytest-asyncio — 184 testes |

---

## Módulos implementados

```
src/
├── models.py          → tipos Pydantic (AcaoTipo, ClassificacaoResult, etc.)
├── classifier.py      → Claude Sonnet 4.6 — 13 ferramentas — tool_use nativo
├── obsidian.py        → REST API + retry exponencial + diário automático
├── whatsapp.py        → Evolution API — parsing webhook + envio
├── transcriber.py     → OpenAI Whisper
├── bot_status.py      → /pausar /ativar por grupo — Postgres async
├── historico.py       → histórico multi-turn em memória — TTL 2h — máx 8 pares
├── dead_letter.py     → fila de falhas — Postgres async — máx 5 tentativas
├── email_reader.py    → IMAP4_SSL Gmail — detecta 2FA, anexos
├── email_digest.py    → Claude Haiku classifica: invoice, task, 2FA, spam
├── briefing.py        → consolida diário + emails + tasks → WhatsApp 8h
├── scheduler.py       → APScheduler asyncio — cron configurável
├── receita.py         → engine YAML → Playwright: click/fill/wait/check
├── configuracoes.py   → configs dinâmicas em Postgres
└── config.py          → pydantic-settings (.env)

api/
└── webhook.py         → FastAPI: /health + /webhook/whatsapp (14 etapas)
```

---

## Variáveis de ambiente

```env
ANTHROPIC_API_KEY       # Claude API
OPENAI_API_KEY          # Whisper
OBSIDIAN_API_KEY        # Obsidian REST API (porta 27124)
EVOLUTION_API_URL       # URL da Evolution API
EVOLUTION_INSTANCE      # Nome da instância WhatsApp
EVOLUTION_API_KEY       # Chave Evolution API
WEBHOOK_SECRET          # Autenticação webhook (x-api-key)
DATABASE_URL            # Postgres (DLQ + BotStatus + Configurações)
```

---

## Rodar localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar a API
uvicorn api.webhook:app --reload --port 8000

# Verificar saúde
curl http://localhost:8000/health

# Rodar todos os testes
python -m pytest tests/ -q

# Simular mensagem de texto
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "key": {"remoteJid": "120363@g.us", "fromMe": false, "participant": "5531@s.whatsapp.net"},
      "pushName": "Luiz",
      "message": {"conversation": "criar task: revisar proposta K2Con até sexta"}
    },
    "groupMetadata": {"subject": "gestao-eg"}
  }'
```

---

## Deploy (Easypanel — Hostinger)

```bash
# Build da imagem
docker build -t integrador-eg .

# Variáveis necessárias no Easypanel:
# ANTHROPIC_API_KEY, OPENAI_API_KEY, OBSIDIAN_API_KEY
# EVOLUTION_API_URL, EVOLUTION_INSTANCE, EVOLUTION_API_KEY
# WEBHOOK_SECRET, DATABASE_URL

# Webhook URL para Evolution API:
# https://[url-easypanel]/webhook/whatsapp
# Header: x-api-key: [WEBHOOK_SECRET]
```

---

## Bloqueadores para produção

1. **Evolution API não configurada** — número +55 31 97224-4045 não conectado
2. **DATABASE_URL** — Postgres em produção não configurado
3. **Deploy Easypanel** — container não subido

Sem esses três, o sistema não processa mensagens reais. O código está pronto e testado.

---

## Base de conhecimento (NotebookLM)

Documentação na pasta `docs/` — otimizada para upload no NotebookLM:

| Arquivo | Conteúdo |
|---------|----------|
| `docs/01-visao-geral-e-arquitetura.md` | Sistema completo, componentes, stack, ações |
| `docs/02-evolution-api-e-whatsapp.md` | Webhook, parsing, modo passivo, autenticação |
| `docs/03-classificador-claude-e-tool-use.md` | 13 ferramentas, multi-turn, prompt caching |
| `docs/04-estado-atual-e-proximos-passos.md` | 184 testes, bloqueadores, histórico |
| `docs/05-grupos-whatsapp-e-projetos.md` | Mapeamento grupos → projetos → Obsidian |

---

## Ecossistema EG

```
EG OS (orquestrador) ←→ Integrador EG (execução) ←→ Obsidian (knowledge base)
        ↑                        ↑
   Claude Code              Evolution API
   (desenvolvimento)         (WhatsApp)
```

- **EG OS:** `C:\Users\user\Desktop\GitHub - Effective Gain\Projetos no Claude\eg_os\`
- **Obsidian vault:** `C:\Users\user\Documents\Effective Gain`
- **n8n:** Easypanel (Hostinger)
- **Notion:** fonte de verdade de documentação pública

---

*Última atualização: 2026-04-23 — 184 testes, 6 grupos mapeados, DNA Obsidian atualizado, docs NotebookLM completos.*

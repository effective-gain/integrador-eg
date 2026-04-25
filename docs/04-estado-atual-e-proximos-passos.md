# Estado Atual e Próximos Passos — Integrador EG

**Última atualização:** 23 de Abril de 2026 | **Commit:** f488297

---

## O que está implementado e funcionando

### Infraestrutura base
- [x] FastAPI com lifespan completo (`api/webhook.py`)
- [x] Endpoint `POST /webhook/whatsapp` — fluxo completo
- [x] Endpoint `GET /health` — status de todos os componentes
- [x] Autenticação via `x-api-key` com hierarquia (DB > .env > dev mode)
- [x] Configurações dinâmicas no Postgres (sem restart do servidor)

### Processamento de mensagens
- [x] Parsing de webhook Evolution API (texto, áudio, imagem, documento)
- [x] Filtro automático: fromMe, DMs, payloads malformados
- [x] Transcrição de áudio via OpenAI Whisper
- [x] Classificação via Claude com tool_use nativo (13 ferramentas)
- [x] Prompt caching (instruções + DNA do projeto)
- [x] Histórico multi-turn por grupo (TTL 2h, máx 8 pares)

### Controle do bot
- [x] Comandos /pausar, /ativar, /status por grupo
- [x] Duração configurável: /pausar 2h, /pausar 30m, /pausar 1h30m
- [x] Auto-reativação por TTL
- [x] Persistência em Postgres (sobrevive a restarts)

### Obsidian
- [x] Leitura de DNA do projeto (contexto para o Claude)
- [x] Escrita de notas, tarefas, reuniões, decisões, lançamentos
- [x] Append em arquivos existentes (tasks, daily)
- [x] Retry com backoff exponencial (3 tentativas)
- [x] Diário de execuções automático

### E-mail
- [x] Leitura de e-mail via IMAP4_SSL (Gmail)
- [x] Classificação de e-mails: invoice, task, 2FA, informativo, spam
- [x] Extração de código 2FA por regex
- [x] Ferramentas de e-mail no classificador (enviar, responder, encaminhar, rascunho)

### Briefing matinal
- [x] APScheduler asyncio com cron configurável
- [x] Consolida: diário do dia anterior + emails + tasks pendentes
- [x] Urgentes aparecem primeiro

### Engine de receitas
- [x] YAML → Playwright: click, fill, select, wait, check_text
- [x] Delay humano entre ações
- [x] Screenshot final de cada execução
- [x] Receita `lancamento_quickbooks.yaml` (17 passos)

### Resiliência
- [x] Dead Letter Queue em Postgres (ações que falharam, reprocessáveis)
- [x] Self-healing: retry automático nas operações Obsidian
- [x] Logs estruturados em todos os módulos

### Qualidade
- [x] 184 testes passando (unitários + integração)
- [x] pytest-asyncio configurado (asyncio_mode = auto)
- [x] Todos os mocks usando asyncpg pattern (sem SQLite em testes)

---

## O que está pendente (próximos passos)

### Deploy e infraestrutura (bloqueadores críticos)
- [ ] Configurar instância Evolution API no Easypanel
- [ ] Conectar +55 31 97224-4045 via QR Code
- [ ] Configurar DATABASE_URL em produção (Postgres)
- [ ] Deploy container no Easypanel (Hostinger)
- [ ] Testar webhook de ponta a ponta com mensagem real

### Criação dos grupos WhatsApp (em ordem de prioridade)
- [ ] `gestao-eg` — primeiro grupo de teste (operação interna EG)
- [ ] `mkt-eg` — marketing interno
- [ ] `k2con` — cliente com maior volume
- [ ] `eg-build` — cliente EUA (QuickBooks integrado)
- [ ] `beef-smash` — cliente EG Food
- [ ] `rodag` — cliente em onboarding

### Funcionalidades
- [ ] Suporte a imagens no webhook (imageMessage)
- [ ] Suporte a documentos/PDFs no webhook (documentMessage)
- [ ] Dashboard web (portal admin) — visualizar diário, DLQ, status

### Integração com plataformas externas
- [ ] QuickBooks — lançamento financeiro via receita Playwright (receita já existe)
- [ ] Buildertrend — lançamentos EG Build (planejado)
- [ ] Social Responder — resposta em redes sociais (em design)

---

## Histórico de versões

### Abril 2026 (atual — commit 06ead0b)
- Migração de bot_status.py de SQLite para Postgres async
- Adição de 4 ferramentas de e-mail no classificador
- Fix: defaultdict → dict no HistoricoConversa
- Fix: AMBIGUA adicionado ao ACAO_EMOJI
- Fix: pytest-asyncio configurado automaticamente
- 184 testes passando (↑ de 135)

### Abril 2026 (commit 92e4202)
- Reescrita completa do classificador: JSON → tool_use nativo
- Implementação de HistoricoConversa (multi-turn)
- Implementação de BotStatus (/pausar, /ativar)
- Merge com branch remoto: email, Outlook, portal admin
- Dead Letter Queue migrado de SQLite para Postgres

### Abril 2026 (commit 3d6677e)
- 135 testes base
- Webhook FastAPI funcionando
- Obsidian integrado com retry
- Briefing matinal com APScheduler

---

## Métricas do projeto

| Métrica | Valor |
|---------|-------|
| Testes | 184 passando |
| Módulos src/ | 15 |
| Ferramentas no classificador | 13 |
| Ações suportadas (AcaoTipo) | 13 |
| Grupos mapeados | 6 |
| Linhas de código (estimado) | ~3.500 |
| Receitas Playwright | 1 (QuickBooks) |

---

## Bloqueadores para produção

1. **Evolution API não configurada** — o número +55 31 97224-4045 ainda não está conectado à instância
2. **DATABASE_URL não configurada** — Postgres em produção pendente (bot_status e DLQ precisam de DB)
3. **OBSIDIAN_API_KEY** — precisa verificar se a API do Obsidian está ativa no servidor

Sem esses três, o sistema não pode processar mensagens reais. Tudo mais está implementado e testado.

---

## Como testar sem WhatsApp

```bash
# Simula uma mensagem de texto
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "key": {"remoteJid": "120363@g.us", "fromMe": false, "participant": "5531@s.whatsapp.net"},
      "pushName": "Luiz",
      "message": {"conversation": "criar task: revisar proposta do cliente até amanhã"}
    },
    "groupMetadata": {"subject": "gestao-eg"}
  }'

# Verifica saúde do sistema
curl http://localhost:8000/health

# Roda todos os testes
python -m pytest tests/ -q
```

---

## Contexto técnico para novos desenvolvedores

O projeto usa:
- **Python 3.12** com type hints estritos
- **FastAPI** com dependências async e lifespan
- **Pydantic v2** para validação de dados
- **asyncpg** para Postgres (não SQLAlchemy)
- **anthropic SDK** para Claude API com tool_use
- **pytest-asyncio** com `asyncio_mode = auto` no pytest.ini
- **Mocks** seguindo o padrão: `AsyncMock` para métodos async, `patch("modulo.get_pool")` para banco

Código de referência: `tests/test_dead_letter.py` e `tests/test_bot_status.py` mostram o padrão correto de mock para Postgres async.

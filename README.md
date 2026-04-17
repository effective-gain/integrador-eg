# Integrador EG

**Effective Gain — Camada de Integração Central**

---

## O que é isso

O Integrador EG é a camada que conecta todos os sistemas da Effective Gain em um fluxo coerente. Ele não é só uma API — é o ponto onde decisões de roteamento acontecem, onde dados de fontes diferentes se encontram, e onde a lógica de negócio da EG vira código executável.

Pensa assim: o EG OS orquestra agentes e define o que fazer. O Integrador EG é o encanamento que faz o dado chegar no lugar certo, na hora certa, no formato certo.

---

## Por que esse projeto existe

A EG opera com múltiplos sistemas que precisam conversar: Notion (fonte de verdade), n8n (automações), Evolution API (WhatsApp), Supabase (banco), Google Sheets (relatórios), NotebookLM (conhecimento). Cada um tem sua API, seu ritmo e seu formato.

Sem uma camada de integração centralizada, cada automação nova vira um Frankenstein — autenticação repetida, lógica duplicada, erros silenciosos. O Integrador EG resolve isso de uma vez.

---

## Linha de raciocínio do projeto

### Decisão 1 — Por que não usar o n8n pra tudo?

O n8n é ótimo para orquestrar fluxos visuais. Mas ele não é a camada certa para lógica de integração complexa, transformação de dados pesada ou reutilização de código entre múltiplos workflows. Usar n8n pra tudo cria acoplamento visual difícil de debugar e impossível de versionar bem.

A decisão foi: **n8n chama o Integrador, o Integrador faz o trabalho pesado.** Isso mantém os workflows do n8n limpos e o código de integração testável e versionado aqui.

### Decisão 2 — Por que não expandir o backend do EG OS?

O EG OS já tem um backend FastAPI focado no orquestrador de agentes. Misturar lógica de integração com lógica de orquestração ia criar um monolito difícil de manter. Manter separado permite que cada peça evolua no seu próprio ritmo.

### Decisão 3 — Autenticação centralizada

Cada serviço externo tem seu segredo. Em vez de espalhar tokens pelo n8n, pelo Notion e pelo Supabase, o Integrador mantém um vault de credenciais e expõe endpoints autenticados. Quem chama o Integrador só precisa de uma chave — a dele.

---

## Módulos ativos

| Módulo | Status | Descrição |
|--------|--------|-----------|
| [WhatsApp OS](#-módulo-whatsapp-os) | ✅ Ativo | Mensagens WhatsApp → Claude → Obsidian |
| [Instagram Keeper](#-módulo-instagram-keeper) | ✅ Ativo | Restauração automática de sessão Instagram |

---

## 📱 Módulo: WhatsApp OS

Transforma mensagens de WhatsApp (texto ou áudio) em ações executadas automaticamente no Obsidian, classificadas por Claude.

### Fluxo completo

```
Grupo WhatsApp (Evolution API)
        │
        ▼
┌───────────────────┐
│   WA_RECEPTOR     │  Webhook recebe mensagem
│                   │  Identifica grupo → projeto
│                   │  Extrai remetente, timestamp
└────────┬──────────┘
         │
    ┌────┴────┐
    │  tipo?  │
    └────┬────┘
   texto │        │ áudio
         │        ▼
         │  ┌─────────────┐
         │  │ WA_WHISPER  │  Download do áudio
         │  │             │  OpenAI Whisper (pt-BR)
         │  │             │  → texto transcrito
         │  └──────┬──────┘
         │         │
         └────┬────┘
              ▼
   ┌─────────────────────┐
   │   WA_CLASSIFIER     │  Envia para Claude Sonnet 4.5
   │                     │  Prompt com contexto do grupo
   │                     │  Retorna JSON estruturado:
   │                     │  { acao, projeto, conteudo,
   │                     │    prioridade, destinatario }
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │   WA_EXECUTOR       │  Monta caminho e conteúdo
   │                     │  PUT  → cria nota nova
   │                     │  POST → append em nota existente
   │                     │  Obsidian REST API (porta 27124)
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │   WA_RESPONDER      │  Gera mensagem de confirmação
   │                     │  com emoji por tipo de ação
   │                     │  Envia de volta ao grupo
   └─────────────────────┘
```

### Ações suportadas

| Ação | Emoji | Destino no Obsidian |
|------|-------|---------------------|
| `criar_nota` | 📝 | `04 - Inbox/{data}-{projeto}.md` |
| `criar_reuniao` | 📅 | `04 - Inbox/Reuniao-{data}-{projeto}.md` |
| `criar_task` | ✅ | append em arquivo de tasks |
| `registrar_decisao` | 🎯 | `03 - Decisoes/{data}-{projeto}.md` |
| `registrar_lancamento` | 💰 | `04 - Inbox/Lancamento-{data}-{projeto}.md` |
| `criar_daily` | 📆 | `06 - Diario/{data}.md` |
| `atualizar_status` | 🔄 | nota existente do projeto |
| `consultar_tasks` | 📋 | leitura via Obsidian API |

### Grupos → Projetos

| Grupo WhatsApp | Projeto mapeado |
|----------------|-----------------|
| `k2con` | K2Con |
| `beef-smash` | Beef Smash & Co |
| `rodag` | RODAG |
| `gestao-eg` | Gestão EG |
| `eg-build` | EG Build (EUA) |
| `mkt-eg` | MKT EG (interno) |

### Workflows n8n

```
workflows/
├── WA_RECEPTOR.json    ← webhook + roteamento de tipo
├── WA_WHISPER.json     ← transcrição de áudio (Whisper)
├── WA_CLASSIFIER.json  ← classificação via Claude Sonnet
├── WA_EXECUTOR.json    ← escrita no Obsidian REST API
└── WA_RESPONDER.json   ← confirmação de volta ao grupo
```

### Variáveis de ambiente necessárias

```env
EVOLUTION_API_URL       # URL da Evolution API
EVOLUTION_INSTANCE      # nome da instância WhatsApp
EVOLUTION_API_KEY       # chave de autenticação
ANTHROPIC_API_KEY       # Claude API
OPENAI_API_KEY          # Whisper transcrição
```

### Scripts de teste

```bash
python scripts/test_obsidian.py     # testa conexão Obsidian REST API
python scripts/test_classifier.py   # testa classificação Claude
python scripts/test_flow.py         # simula fluxo completo sem WhatsApp
```

---

## 📸 Módulo: Instagram Keeper

Resolve o gargalo de sessão expirada: quando o Instagram derruba a sessão do Chrome após inatividade, o Cowork (Claude Code) perde acesso para responder mensagens. Esta automação restaura o login automaticamente a cada 30 minutos.

### Problema

O Instagram derruba sessões do Chrome após períodos de inatividade. Quando o Cowork tenta executar uma resposta no Instagram, a aba está na tela de login e a ação falha silenciosamente.

### Fluxo completo

```
n8n Schedule (a cada 30 min)
        │
        ▼
┌───────────────────────────────┐
│  Checar Sessão Instagram      │
│  python instagram_keeper.py   │
│  --status                     │
│                               │
│  Abre Chrome com perfil salvo │
│  Navega para                  │
│  instagram.com/accounts/edit/ │
│  Detecta se há login form     │
└──────────────┬────────────────┘
               │
       ┌───────┴────────┐
       │  exit code?    │
       └───────┬────────┘
          0    │    1
    (logado)   │  (expirado)
        ↓      │
   (encerra)   ▼
       ┌─────────────────────────┐
       │   Restaurar Login       │
       │   python instagram_     │
       │   keeper.py             │
       │                         │
       │   1. Abre Chrome com    │
       │      perfil salvo       │
       │   2. Navega para        │
       │      instagram.com      │
       │   3. Aciona autofill    │
       │      nativo do Chrome   │
       │      (senha salva no    │
       │      gerenciador)       │
       │   4. Submete formulário │
       └──────────┬──────────────┘
                  │
         ┌────────┴────────┐
         │    sucesso?     │
         └────────┬────────┘
            SIM   │   NÃO
             ↓         ↓
     Log ✅ Obsidian   Alerta WhatsApp
                       → +55 31 97224-4045
                       Log ❌ Obsidian
```

### Comportamento por cenário

| Cenário | O que acontece |
|---------|----------------|
| Sessão ativa | Script encerra com código 0, n8n não executa restauração |
| Sessão expirada + senha salva no Chrome | Chrome abre, autofill preenche, login restaurado automaticamente |
| Sessão expirada + senha NÃO salva | Falha, alerta WhatsApp enviado para Luiz |
| Chrome fora do PATH | Erro no script, alerta WhatsApp |

### Comandos manuais

```bash
# Verificar status da sessão (sem restaurar)
python scripts/instagram_keeper.py --status

# Verificar e restaurar se necessário (uma vez)
python scripts/instagram_keeper.py

# Loop contínuo a cada 20 minutos (alternativa ao n8n)
python scripts/instagram_keeper.py --loop 20
```

### Configuração inicial

1. Abrir Chrome manualmente e fazer login no Instagram
2. Salvar a senha no gerenciador do Chrome quando solicitado
3. Confirmar em `chrome://password-manager` que `instagram.com` aparece
4. Importar `workflows/INSTA_KEEPER.json` no n8n e ativar

### Arquivos

```
workflows/
└── INSTA_KEEPER.json       ← schedule + check + restore + alertas WhatsApp

scripts/
└── instagram_keeper.py     ← script Python completo com Playwright
```

### Log de execuções

Cada execução é registrada automaticamente em `Obsidian → 04 - Inbox/Instagram-Keeper-Log.md`.

---

## Estrutura do repositório

```
integrador-eg/
├── workflows/
│   ├── WA_RECEPTOR.json
│   ├── WA_WHISPER.json
│   ├── WA_CLASSIFIER.json
│   ├── WA_EXECUTOR.json
│   ├── WA_RESPONDER.json
│   └── INSTA_KEEPER.json
├── scripts/
│   ├── instagram_keeper.py
│   ├── test_obsidian.py
│   ├── test_classifier.py
│   └── test_flow.py
├── prompts/
│   ├── classifier.md
│   └── responder.md
└── README.md
```

---

## Stack

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| Workflows | n8n self-hosted (Easypanel) | Orquestração visual |
| AI Classifier | Claude Sonnet 4.5 | Classificação de intenção |
| Transcrição | OpenAI Whisper | Áudio pt-BR |
| WhatsApp | Evolution API | Unofficial WhatsApp API |
| Knowledge Base | Obsidian REST API (porta 27124) | Base local de conhecimento |
| Browser Automation | Playwright + Chrome profile | Sessão Instagram |
| Framework futuro | FastAPI + Pydantic v2 | Endpoints centralizados |
| Deploy | Easypanel (Hostinger) | Alinhado com infra EG |

---

## Como este README funciona

Este arquivo é atualizado a cada mudança significativa de direção. Ele documenta o **raciocínio** por trás das decisões — não só o que foi feito, mas por que foi feito assim e o que foi descartado.

Se você está lendo isso depois que o projeto já cresceu: o histórico de commits complementa este README. Cada commit importante tem uma mensagem que explica o contexto, não só a mudança.

---

## Status atual

> **Fase:** Módulos WhatsApp OS e Instagram Keeper implementados e documentados.

Próximos passos:
1. Ativar workflows no n8n (importar os 6 JSONs de `workflows/`)
2. Configurar variáveis de ambiente no n8n
3. Testar com `python scripts/test_flow.py`
4. Expandir para novos canais (Telegram, email)

---

*Última atualização: 2026-04-17 — Módulos WhatsApp OS e Instagram Keeper adicionados com fluxos completos.*

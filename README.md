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

## O produto: o que ele faz na prática

### O fluxo completo

1. Um cliente premium ou fornecedor envia uma mensagem (texto ou áudio) em um grupo de WhatsApp dedicado
2. A mensagem é capturada pela Evolution API
3. Um agente interpreta a mensagem e entende a intenção
4. Se faltam detalhes, o agente responde no próprio grupo pedindo confirmação antes de agir — **nunca executa no escuro**
5. Com a ação confirmada, o agente executa a tarefa no sistema de destino (portal externo, rede social, Obsidian, etc.)
6. A ação executada é documentada no Obsidian (diário do projeto) para rastreabilidade e análise de volume
7. O orquestrador distribui as ações entre os agentes disponíveis conforme a demanda

### Grupos por projeto/cliente

Cada projeto ou cliente premium tem seu próprio grupo de WhatsApp. Exemplos reais:
- **Grupo K2Con** → ações específicas do projeto K2Con
- **Grupo QuickBooks** → fornecedor envia "5 cliff" (invoice) → agente faz login no QuickBooks e lança o valor automaticamente

Essa separação por grupo é arquitetural, não só organizacional. O grupo define o contexto: o agente sabe qual workflow executar, com quais credenciais, em qual sistema.

### O papel do Obsidian

O Obsidian roda localmente nesta máquina, 24/7, e tem dois papéis:

1. **Workflow designer** — cada ação possível é desenhada caso a caso dentro do Obsidian. É o "manual de instruções" de cada automação: o que fazer, quando fazer, quais passos seguir, quais exceções tratar.
2. **Diário de execuções** — toda ação executada é registrada com data, hora, origem (grupo), ação realizada e resultado. Isso gera histórico para entender volume, recorrência e necessidade de escalar.

### O mecanismo de confirmação

Antes de executar qualquer ação que envolva sistemas externos (login, lançamento, resposta pública), o agente envia uma mensagem de volta ao grupo:

> *"Você solicitou [ação X]. Posso dar prosseguimento?"*

O cliente confirma e só então a execução acontece. Esse comportamento é padrão e pode ser desativado por ação específica quando a confiança estiver estabelecida.

### Tipo de ações possíveis

- Entrar em uma página web, fazer login e executar uma ação específica (ex: QuickBooks, portais de fornecedores)
- Responder clientes em redes sociais em tempo real — sem API oficial, via automação de browser
- Criar, atualizar ou consultar registros em sistemas integrados
- Áudio ou texto como gatilho — ambos são suportados

---

## Linha de raciocínio do projeto

### Decisão 1 — Por que não usar o n8n pra tudo?

O n8n é ótimo para orquestrar fluxos visuais. Mas ele não é a camada certa para lógica de integração complexa, transformação de dados pesada ou reutilização de código entre múltiplos workflows. Usar n8n pra tudo cria acoplamento visual difícil de debugar e impossível de versionar bem.

A decisão foi: **n8n chama o Integrador, o Integrador faz o trabalho pesado.** Isso mantém os workflows do n8n limpos e o código de integração testável e versionado aqui.

### Decisão 2 — Por que não expandir o backend do EG OS?

O EG OS já tem um backend FastAPI focado no orquestrador de agentes. Misturar lógica de integração com lógica de orquestração ia criar um monolito difícil de manter. Manter separado permite que cada peça evolua no seu próprio ritmo.

### Decisão 3 — Autenticação centralizada

Cada serviço externo tem seu segredo. Em vez de espalhar tokens pelo n8n, pelo Notion e pelo Supabase, o Integrador mantém um vault de credenciais e expõe endpoints autenticados. Quem chama o Integrador só precisa de uma chave — a dele.

### Decisão 4 — Grupo de WhatsApp como contexto de execução

A decisão de usar um grupo por projeto não é só organizacional — é arquitetural. O grupo define o contexto. O agente não precisa perguntar "qual projeto é esse?" porque o grupo já responde. Isso simplifica o roteamento e elimina ambiguidade na entrada.

### Decisão 5 — Confirmação antes da execução (por padrão)

Ações que afetam sistemas externos são irreversíveis ou difíceis de desfazer. A confirmação prévia protege o cliente e a EG de execuções erradas. É um custo baixo (uma mensagem a mais) com benefício alto (confiança e rastreabilidade).

### Decisão 6 — Obsidian como cérebro local, rodando 24/7

O Obsidian já está instalado e com workflows desenhados nesta máquina. Usá-lo como camada de design e documentação aproveita o que já existe. O diário de execuções resolve o problema de rastreabilidade sem precisar de um banco externo — pelo menos na fase inicial.

### Decisão 7 — Redes sociais sem API oficial

As APIs oficiais de redes sociais (Instagram, Facebook, TikTok) são restritivas: exigem aprovação de app, têm rate limits baixos e podem ser revogadas por mudança de política a qualquer momento.

A alternativa é automação de browser com Playwright: o agente abre o navegador com um perfil com sessão ativa e age como um humano faria. O custo é maior em complexidade (manutenção de sessão, cuidados com detecção), mas a liberdade é total — sem dependência de aprovação de plataforma. O Instagram Keeper já prova que esse padrão funciona.

---

## Módulos ativos

| Módulo | Status | Descrição |
|--------|--------|-----------|
| [WhatsApp OS](#-módulo-whatsapp-os) | ✅ Ativo | Mensagens WhatsApp → Claude → Obsidian |
| [Instagram Keeper](#-módulo-instagram-keeper) | ✅ Ativo | Restauração automática de sessão Instagram |
| [Social Responder](#-módulo-social-responder-planejado) | 🔜 Planejado | Resposta a clientes em redes sociais via browser |

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

## 🔜 Módulo: Social Responder (planejado)

### O que será

Um módulo que monitora e responde mensagens e comentários em redes sociais (Instagram, Facebook, TikTok, LinkedIn) em tempo real — sem API oficial, via automação de browser com Playwright.

### Por que sem API oficial

As APIs oficiais são restritivas: exigem aprovação de app (semanas a meses), têm rate limits baixos, escopo limitado por tipo de conta, e podem ser revogadas por mudança de política. Para um produto de resposta em tempo real para múltiplos clientes isso cria dependência e fragilidade.

A abordagem via browser é mais robusta: o agente navega com uma sessão ativa e age como um humano faria.

### Desafios a resolver (em design)

1. **Gestão de sessão** — cada rede social precisa de um perfil Chrome com sessão persistente. O Instagram Keeper já prova esse padrão.
2. **Humanização** — redes sociais detectam bots por cadência de ação, user agent e ausência de movimentos de mouse. Estratégias: delays variáveis, movimentos simulados.
3. **Leitura de notificações** — cada plataforma tem seu layout. O módulo precisa saber onde estão as mensagens não lidas.
4. **Contexto da resposta** — o agente lê o histórico da conversa ou o post original antes de gerar a resposta.
5. **Confirmação antes de postar** — respostas públicas ou em DM passam pelo mecanismo de confirmação no WhatsApp antes de serem publicadas.

### Redes sociais previstas

| Rede | Prioridade | Tipo de interação |
|------|-----------|-------------------|
| Instagram | Alta | DMs + comentários |
| Facebook | Média | Comentários + Messenger |
| TikTok | Média | Comentários |
| LinkedIn | Baixa | Mensagens |

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
├── connectors/         ← um conector por serviço externo
├── routes/             ← endpoints FastAPI
├── schemas/            ← Pydantic models
├── tests/              ← testes por conector
└── docs/               ← decisões técnicas e contratos de API
```

---

## Stack

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| Workflows | n8n self-hosted (Easypanel) | Orquestração visual |
| AI Classifier | Claude Sonnet 4.5 | Classificação de intenção + geração de respostas |
| Transcrição | OpenAI Whisper | Áudio pt-BR |
| WhatsApp | Evolution API | Unofficial WhatsApp API |
| Knowledge Base | Obsidian REST API (porta 27124) | Workflows + diário de execuções |
| Browser Automation | Playwright + Chrome profile | Portais externos + redes sociais sem API oficial |
| Framework futuro | FastAPI + Pydantic v2 | Endpoints centralizados |
| Deploy | Easypanel (Hostinger) | Alinhado com infra EG |
| Disponibilidade | 24/7 | Máquina local sempre ligada |

---

## Como este README funciona

Este arquivo é atualizado a cada ideia, decisão ou mudança de direção — inclusive durante conversas de planejamento. Ele documenta o **raciocínio** por trás das decisões — não só o que foi feito, mas por que foi feito assim e o que foi descartado.

Se você está lendo isso depois que o projeto já cresceu: o histórico de commits complementa este README. Cada commit importante tem uma mensagem que explica o contexto, não só a mudança.

---

## Status atual

> **Fase:** WhatsApp OS e Instagram Keeper ativos. Social Responder em design — abordagem via browser definida, desafios mapeados.

Próximos passos:
1. Ativar workflows no n8n (importar os JSONs de `workflows/`)
2. Mapear ações do QuickBooks (primeiro portal externo)
3. Iniciar design detalhado do Social Responder (Instagram primeiro)
4. Testar com `python scripts/test_flow.py`

---

*Última atualização: 2026-04-17 — Produto estruturado: grupos WhatsApp por projeto, confirmação prévia, Obsidian 24/7. Social Responder adicionado: resposta em redes sociais via browser sem API oficial.*

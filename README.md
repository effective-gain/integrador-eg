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
- Receber documentos (cupons fiscais, invoices, arquivos) e lançar na plataforma correta
- Responder clientes em redes sociais em tempo real — sem API oficial, via automação de browser
- Criar, atualizar ou consultar registros em sistemas integrados
- Enviar resumo diário de todas as ações executadas para o cliente
- Áudio, texto ou arquivo como gatilho — todos são suportados

### Briefing matinal

Todo cliente pode ter um **briefing automático enviado via WhatsApp às 8h do dia seguinte**. O conteúdo é dinâmico e definido conforme a forma de trabalho de cada cliente. Um exemplo real:

- Resumo de todas as ações executadas no dia anterior
- E-mails recebidos que ainda não tiveram resposta ou ação
- Questões em aberto que precisam de decisão
- Tarefas pendentes do dia

O horário e o conteúdo do briefing são configurados no cofre do cliente no Obsidian e podem mudar conforme a dinâmica evolui. O cliente começa o dia já informado, sem precisar abrir nenhum sistema.

---

### Exemplo real: lançamento de cupom fiscal

Este é o fluxo que melhor ilustra o produto funcionando de ponta a ponta:

```
Cliente envia cupom fiscal no grupo WhatsApp
        │
        ▼
Agente recebe via Evolution API
Identifica: tipo = documento fiscal, cliente = [nome]
        │
        ▼
Agente responde no grupo:
"Recebi um cupom fiscal de R$ [valor] — [fornecedor].
Posso lançar na plataforma financeira?"
        │
        ▼
Cliente responde: OK
        │
        ▼
Agente abre a plataforma financeira via browser
Faz login com as credenciais do cofre do cliente
Navega até a posição correta
Sobe o arquivo e preenche os campos necessários
        │
        ▼
Registra a ação no diário do cliente no Obsidian:
[data/hora] Cupom fiscal lançado — R$ [valor] — [fornecedor]
        │
        ▼
Ao final do dia:
Agente envia resumo no grupo WhatsApp com
todas as ações executadas naquele dia
```

O que torna esse fluxo poderoso não é a ação em si — é que **ele é desenhado uma vez e executado infinitas vezes**, de forma autônoma, com rastreabilidade completa. O cliente nunca precisa acessar a plataforma financeira diretamente.

---

### Receita de automação — o padrão de desenho

Para que o agente possa executar qualquer ação em qualquer site, cada automação precisa ser descrita como uma **receita**. Essa receita fica no cofre do cliente no Obsidian e é o que o agente lê antes de executar.

Toda receita tem obrigatoriamente cinco elementos:

```
RECEITA: [nome da automação]
─────────────────────────────────────────────
GATILHO
  O que dispara esta automação.
  Ex: cliente envia arquivo .pdf no grupo WhatsApp

URL
  Endereço exato do sistema onde a ação será executada.
  Ex: https://app.quickbooks.com/...

CREDENCIAIS
  Onde estão as credenciais de acesso.
  Sempre salvas no cofre do cliente no Obsidian.
  Nunca escritas diretamente na receita.
  Ex: Cofre/[cliente]/Credenciais/QuickBooks

PASSO A PASSO
  Descrição exata do que fazer, em ordem.
  Quanto mais específico, mais confiável a execução.
  Ex:
    1. Abrir URL e fazer login com as credenciais
    2. Navegar para Despesas > Nova despesa
    3. Preencher: fornecedor, valor, data (extraídos do arquivo)
    4. Anexar o arquivo recebido
    5. Clicar em Salvar

SAÍDA
  O que registrar após a execução e onde.
  Ex:
    - Registrar em: Diário do cliente > [data] > Lançamentos
    - Confirmar no grupo: "Cupom fiscal de R$ [valor] lançado ✅"
    - Incluir no briefing das 8h do dia seguinte
```

Esse formato é a base de todo o sistema. A EG desenha a receita, testa, valida com o cliente e coloca no cofre. A partir daí, o agente executa sozinho sempre que o gatilho acontecer.

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

Um módulo que monitora e responde mensagens e comentários em **todas as redes sociais** (Instagram, Facebook, TikTok, LinkedIn, e outras) em tempo real — sem API oficial, via automação de browser com Playwright, com respostas geradas pelo Claude via API.

### Como funciona a resposta

Cada cliente tem seu próprio **prompt específico** configurado no sistema. Esse prompt define a personalidade, o tom, o escopo de assuntos e os limites do que o agente pode e não pode responder. O bot usa a Claude API com esse prompt como contexto e responde de forma autônoma — sem precisar de confirmação humana para cada mensagem, pois o prompt já é o "contrato" de comportamento.

O volume de interações é dinâmico e varia de acordo com a realidade de cada cliente. O sistema escala conforme a demanda.

### Por que sem API oficial

As APIs oficiais são restritivas: exigem aprovação de app (semanas a meses), têm rate limits baixos, escopo limitado por tipo de conta, e podem ser revogadas por mudança de política. Para um produto de resposta em tempo real para múltiplos clientes, isso cria dependência e fragilidade.

A abordagem via browser é mais robusta: o agente navega com uma sessão ativa e age como um humano faria — lê o que aparece na tela, entende o contexto e responde.

### O cofre do cliente no Obsidian

Cada cliente tem seu próprio **cofre no Obsidian** — um vault dedicado que funciona como o DNA completo daquele cliente. Não é só um prompt. É o detalhamento de:

- Como o cliente pensa e se comunica
- Tom de voz, vocabulário, valores da marca
- Processos de trabalho repetitivos que serão executados de forma autônoma
- Histórico de decisões e contexto acumulado
- Receitas de automação: cada ação mapeada com gatilho, URL, credenciais, passo a passo e saída
- Limites do que o agente pode e não pode fazer para aquele cliente

Esse cofre alimenta o Claude com contexto rico antes de cada ação. O agente não age no escuro — age com o DNA do cliente carregado. O Obsidian é o repositório vivo desse conhecimento, e ele cresce com o tempo à medida que a EG aprende mais sobre cada cliente.

**O cofre nunca é acessado pelo cliente.** Ele é a inteligência da EG — o mecanismo que entrega o resultado. O cliente vê o output, não o processo. Dar acesso ao cofre seria entregar o produto inteiro: o cliente poderia replicar o serviço internamente ou apresentar o modelo para outro fornecedor, quebrando o vínculo de recorrência. A caixa preta é intencional e é o que mantém o contrato.

### Gestão de sessão (transparente para o cliente)

Quando uma sessão cai em qualquer rede social, o sistema EG restaura automaticamente — sem notificar o cliente. A restauração segue a dinâmica definida para cada cliente (horários, frequência, comportamento esperado). O cliente só sabe que o serviço está rodando. A EG cuida da infraestrutura de forma invisível.

### Desenvolvimento e validação do prompt

O fluxo de construção do prompt de cada cliente é:
1. **EG desenvolve** — com base no cofre do cliente no Obsidian, no DNA da marca e nos objetivos definidos
2. **EG valida tecnicamente** — testa, ajusta e garante que o comportamento está correto antes de apresentar
3. **Cliente verifica** — vê o resultado final funcionando e diz se está ok. Não vê o mecanismo, só o output
4. **Deploy** — prompt homologado entra em produção

### Guardrails globais (parâmetros fixos para todos os clientes)

Os guardrails são baseados no próprio DNA da EG — os mesmos princípios, ética e forma de trabalhar que a EG usa em tudo que faz. Nenhum cliente pode configurar um comportamento que vá contra esses parâmetros. O que a EG não faria para si mesma, não faz para nenhum cliente.

Isso significa que os guardrails não precisam ser uma lista arbitrária de regras — eles emergem naturalmente do cofre da EG no Obsidian, que já documenta como a EG pensa e age.

### Arquitetura por cliente

Cada cliente tem:
- **Cofre dedicado no Obsidian** — DNA completo: tom, processos, contexto, limites
- **Perfil Chrome** com sessão ativa nas redes sociais configuradas
- **Prompt homologado** — desenvolvido pela EG, testado e aprovado pelo cliente
- **Dinâmica de operação** — frequência, horários e comportamento específicos para aquele cliente

### Desafios a resolver (em design)

1. **Gestão de sessão** — cada rede social por cliente precisa de um perfil Chrome com sessão persistente. O Instagram Keeper já prova esse padrão.
2. **Humanização** — redes sociais detectam bots por cadência e comportamento. Estratégias: delays variáveis, intervalos realistas entre respostas.
3. **Leitura de notificações** — cada plataforma tem seu layout e muda. O módulo precisa ser resiliente a mudanças de UI.
4. **Contexto da resposta** — o agente lê o histórico da conversa ou o post original antes de gerar a resposta, com o cofre do cliente carregado como contexto.
5. **Versionamento de prompt** — mudanças de tom ou escopo de um cliente precisam ser aplicadas sem interromper o sistema. O cofre do Obsidian é a fonte de verdade.

### Redes sociais previstas

| Rede | Prioridade | Tipo de interação |
|------|-----------|-------------------|
| Instagram | Alta | DMs + comentários |
| Facebook | Alta | Comentários + Messenger |
| TikTok | Média | Comentários |
| LinkedIn | Média | Mensagens |
| Outras | Conforme cliente | A definir |

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

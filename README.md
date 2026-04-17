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
5. Com a ação confirmada e bem definida, o agente executa a tarefa no sistema de destino (ex: login no QuickBooks e lançamento de invoice)
6. A ação executada é documentada no Obsidian (diário do projeto) para rastreabilidade e análise de volume
7. O orquestrador distribui as ações entre os agentes disponíveis conforme a demanda

### Grupos por projeto/cliente

Cada projeto ou cliente premium tem seu próprio grupo de WhatsApp. Exemplos reais:
- **Grupo K2Con** → ações específicas do projeto K2Con
- **Grupo QuickBooks** → fornecedor envia "5 cliff" (invoice) → agente faz login no QuickBooks e lança o valor automaticamente

Essa separação por grupo serve como contexto. O agente sabe em qual grupo está e, portanto, sabe qual workflow executar, com quais credenciais, em qual sistema.

### O papel do Obsidian

O Obsidian roda localmente nesta máquina, 24/7, e tem dois papéis:

1. **Workflow designer** — cada ação possível é desenhada caso a caso dentro do Obsidian. É onde fica o "manual de instruções" de cada automação: o que fazer, quando fazer, quais passos seguir, quais exceções tratar.
2. **Diário de execuções** — toda ação executada é registrada no diário do Obsidian com data, hora, origem (grupo), ação realizada e resultado. Isso gera histórico para entender volume, recorrência e necessidade de escalar.

### O mecanismo de confirmação

Antes de executar qualquer ação que envolva sistemas externos (login, lançamento, alteração), o agente envia uma mensagem de volta ao grupo:

> *"Você solicitou [ação X]. Posso dar prosseguimento?"*

Isso protege contra mensagens ambíguas, erros de interpretação e ações irreversíveis. O cliente confirma e só então a execução acontece. Esse comportamento é padrão, mas pode ser desativado por ação específica quando a confiança estiver estabelecida.

### Tipo de ações possíveis

As ações são desenhadas caso a caso, mas o padrão é:
- Entrar em uma página web, fazer login e executar uma ação específica (ex: QuickBooks, fornecedores, portais)
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

Ações que afetam sistemas externos são irreversíveis ou difíceis de desfazer. A confirmação prévia no próprio grupo protege o cliente e a EG de execuções erradas. É um custo baixo (uma mensagem a mais) com um benefício alto (confiança e rastreabilidade).

### Decisão 6 — Obsidian como cérebro local, rodando 24/7

O Obsidian já está instalado e com workflows desenhados nesta máquina. Usá-lo como camada de design e documentação aproveita o que já existe. O diário de execuções resolve o problema de rastreabilidade sem precisar de um banco externo para isso — pelo menos na fase inicial.

---

## O que este repositório vai conter

- **`/src`** — código fonte das integrações
- **`/connectors`** — um conector por serviço externo (Notion, Supabase, n8n, Evolution API, Google Sheets, NotebookLM, QuickBooks)
- **`/routes`** — endpoints FastAPI expostos para o n8n e o EG OS chamarem
- **`/schemas`** — Pydantic models para validação de entrada e saída
- **`/tests`** — testes por conector
- **`/docs`** — decisões técnicas e contratos de API
- **`/workflows`** — mapeamento dos workflows por grupo/projeto (espelho do que está no Obsidian)

---

## Stack prevista

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| Framework | FastAPI | Consistência com EG OS · async nativo |
| Validação | Pydantic v2 | Tipagem forte · erros claros |
| HTTP client | httpx | Async · retry built-in |
| Auth | JWT + API Keys | Simples de rotear via n8n |
| Secrets | `.env` + vault futuro | Começar simples |
| Deploy | Easypanel (Hostinger) | Alinhado com o resto da infra EG |
| WhatsApp | Evolution API | Já em uso na EG |
| Automação web | Playwright | Login e ações em portais externos |
| Documentação local | Obsidian | Workflows + diário de execuções |
| Disponibilidade | 24/7 | Máquina local sempre ligada |

---

## Como este README funciona

Este arquivo é atualizado a cada ideia, decisão ou mudança de direção — inclusive durante conversas de planejamento. Ele documenta o **raciocínio** por trás das decisões — não só o que foi feito, mas por que foi feito assim e o que foi descartado.

Se você está lendo isso depois que o projeto já cresceu: o histórico de commits complementa este README. Cada commit importante tem uma mensagem que explica o contexto, não só a mudança.

---

## Status atual

> **Fase:** Estruturação — produto definido, arquitetura sendo desenhada.

Próximos passos:
1. Definir os primeiros grupos/projetos prioritários e seus workflows
2. Mapear as ações do QuickBooks (primeiro caso de uso real)
3. Criar estrutura de pastas e esqueleto FastAPI
4. Primeiro endpoint: receber mensagem da Evolution API e rotear pelo grupo

---

*Última atualização: 2026-04-17 — Produto estruturado: grupos WhatsApp por projeto, agente com confirmação prévia, Obsidian como workflow designer e diário de execuções, ações web via Playwright.*

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

## O que este repositório vai conter

- **`/src`** — código fonte das integrações
- **`/connectors`** — um conector por serviço externo (Notion, Supabase, n8n, Evolution API, Google Sheets, NotebookLM)
- **`/routes`** — endpoints FastAPI expostos para o n8n e o EG OS chamarem
- **`/schemas`** — Pydantic models para validação de entrada e saída
- **`/tests`** — testes por conector
- **`/docs`** — decisões técnicas e contratos de API

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

---

## Como este README funciona

Este arquivo é atualizado a cada mudança significativa de direção. Ele documenta o **raciocínio** por trás das decisões — não só o que foi feito, mas por que foi feito assim e o que foi descartado.

Se você está lendo isso depois que o projeto já cresceu: o histórico de commits complementa este README. Cada commit importante tem uma mensagem que explica o contexto, não só a mudança.

---

## Status atual

> **Fase:** Inicialização — repositório criado, estrutura sendo definida.

Próximos passos:
1. Definir os primeiros conectores prioritários (Notion + Supabase)
2. Criar estrutura de pastas e esqueleto FastAPI
3. Primeiro endpoint: health check + validação de credenciais

---

*Última atualização: 2026-04-17 — Repositório criado. Estrutura e linha de raciocínio inicial documentadas.*

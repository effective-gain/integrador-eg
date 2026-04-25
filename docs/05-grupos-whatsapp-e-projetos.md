# Grupos WhatsApp e Projetos — Estrutura de Operação

**Projeto:** Integrador EG | **Atualizado:** Abril 2026

---

## Modelo de operação

Cada projeto ativo na Effective Gain tem um **grupo de WhatsApp dedicado**. Toda mensagem enviada no grupo é interceptada pela Evolution API, processada pelo Claude Sonnet 4.6, e executada no Obsidian — sem nenhuma interface adicional.

O grupo define o contexto automaticamente. O sistema identifica qual projeto é pelo nome do grupo, carrega o DNA do projeto no Obsidian, e classifica a intenção com precisão.

**Número EG:** +55 31 97224-4045 (Evolution API — a configurar)

---

## Grupos e mapeamento de projetos

| Grupo WhatsApp | ID no sistema | Projeto | DNA Obsidian | NotebookLM |
|----------------|--------------|---------|--------------|------------|
| k2con | `k2con` | K2Con | `01 - Projetos/K2Con.md` | `72edea74` |
| beef-smash | `beef-smash` | EG Food (Beef Smash & Co) | `01 - Projetos/EG Food.md` | `d5eb240a` |
| rodag | `rodag` | RODAG | `01 - Projetos/RODAG.md` | `3cf62a11` |
| gestao-eg | `gestao-eg` | Gestão EG | `01 - Projetos/Gestao EG.md` | `06d696cd` |
| eg-build | `eg-build` | EG Build OS | `01 - Projetos/EG Build OS.md` | `2a5a0210` |
| mkt-eg | `mkt-eg` | MKT EG | `01 - Projetos/MKT EG.md` | `0ebd3fd5` |

---

## Como o sistema identifica o projeto

O campo `groupMetadata.subject` do webhook Evolution API contém o nome do grupo. O sistema busca uma substring desse nome no dicionário de mapeamento:

```python
GRUPOS_PROJETOS = {
    "k2con":      "K2Con",
    "beef-smash": "Beef Smash & Co",
    "rodag":      "RODAG",
    "gestao-eg":  "Gestão EG",
    "eg-build":   "EG Build",
    "mkt-eg":     "MKT EG",
}
```

**Exemplos de nomes de grupo que funcionam:**
- "K2Con - Projeto" → detecta "k2con" → projeto K2Con ✅
- "Beef Smash time" → detecta "beef-smash" → projeto EG Food ✅
- "Reunião RODAG" → detecta "rodag" → projeto RODAG ✅

---

## Ações disponíveis por grupo

### Ações universais (todos os grupos)

| O que dizer | Ação | Onde vai no Obsidian |
|-------------|------|---------------------|
| "criar nota: [conteúdo]" | criar_nota | `04 - Inbox/{data}-{projeto}.md` |
| "reunião: [pauta]" | criar_reuniao | `04 - Inbox/Reuniao-{data}-{projeto}.md` |
| "task: [descrição]" | criar_task | `05 - Tasks/{projeto}-tasks.md` |
| "decisão: [o que foi decidido]" | registrar_decisao | `03 - Decisoes/{data}-{projeto}.md` |
| "status: [atualização]" | atualizar_status | `02 - Projetos/{projeto}/status.md` |
| "quais tasks abertas?" | consultar_tasks | leitura de `05 - Tasks/{projeto}-tasks.md` |
| "daily: [atualização do dia]" | criar_daily | `06 - Diario/{data}.md` |

### Ações financeiras (gestao-eg, eg-build, beef-smash)

| O que dizer | Ação | Campos extraídos |
|-------------|------|-----------------|
| "despesa R$1500 fornecedor X..." | registrar_lancamento | valor, tipo, categoria, fornecedor, vencimento |
| "recebi R$3000 do cliente Y" | registrar_lancamento | valor=3000, tipo=receita |

### Ações de e-mail (todos os grupos)

| O que dizer | Ação |
|-------------|------|
| "manda email para [pessoa] sobre [assunto]" | enviar_email |
| "responde o email de [pessoa] dizendo [conteúdo]" | responder_email |
| "cria rascunho de email para [pessoa]" | criar_rascunho |

### Controle do bot (qualquer grupo)

| Comando | Efeito |
|---------|--------|
| `/pausar` | Pausa o bot indefinidamente neste grupo |
| `/pausar 2h` | Pausa por 2 horas |
| `/pausar 30m` | Pausa por 30 minutos |
| `/pausar 1h30m` | Pausa por 1h30 |
| `/ativar` | Reativa o bot |
| `/status` | Mostra se bot está ativo ou pausado |

---

## DNA por projeto — o que o Claude carrega antes de classificar

Para cada grupo, o Claude lê o DNA do projeto em `01 - Projetos/{projeto}.md` antes de classificar. Isso permite:

- **K2Con:** sabe que é SaaS de consórcios, que tem bugs P0 pendentes, que usa Next.js + Supabase
- **Gestão EG:** sabe que é financeiro multi-empresa, que usa Go + Next.js, clientes: Allp Fit, Amor Saúde, Cartão de Todos
- **RODAG:** sabe que é distribuidora diesel, foco em marketing B2B, CRM com follow-up WhatsApp
- **EG Build:** sabe que é ERP construção civil EUA, integração QuickBooks, 12 módulos em produção

Mensagens ambíguas se tornam precisas porque o Claude tem contexto real do projeto.

---

## Histórico multi-turn por grupo

Cada grupo tem seu próprio histórico de conversa em memória (TTL 2 horas, máx 8 turnos). Isso permite:

```
Luiz: criar task: revisar contrato K2Con
Bot: ✅ Task criada — revisar contrato K2Con

Luiz: adiciona mais uma igual mas com prazo sexta
Bot: ✅ Task criada — revisar contrato K2Con (prazo: sexta)
```

O Claude entende a referência "mais uma igual" porque tem o histórico do turno anterior.

---

## Roteiro de criação dos grupos

### Pré-requisito: configurar Evolution API

```
1. Deploy do Integrador EG no Easypanel (Hostinger)
2. Criar instância na Evolution API
3. Conectar +55 31 97224-4045 via QR Code
4. Configurar webhook:
   URL: https://[url-integrador]/webhook/whatsapp
   Header: x-api-key: [WEBHOOK_SECRET]
   Evento: MESSAGES_UPSERT
```

### Ordem de criação dos grupos (por prioridade)

1. **gestao-eg** — primeiro grupo de teste (operação interna EG)
2. **mkt-eg** — marketing interno
3. **k2con** — cliente com maior volume de interações
4. **eg-build** — cliente EUA (QuickBooks integrado)
5. **beef-smash** — cliente EG Food
6. **rodag** — cliente em onboarding

### Como criar cada grupo

```
1. Criar grupo WhatsApp com o nome correto (ex: "gestao-eg")
2. Adicionar +55 31 97224-4045 como participante
3. Adicionar membros da equipe EG que vão usar
4. Enviar mensagem de teste: "criar nota: teste do sistema"
5. Verificar no Obsidian se a nota apareceu em 04 - Inbox/
6. Testar /status para ver se bot responde
```

---

## Modo de operação: passivo (sem resposta)

Por padrão, o Integrador opera em **modo passivo** — recebe, processa e registra no Obsidian, sem enviar resposta de volta ao grupo. Isso é:

- **Seguro:** não aciona nenhum mecanismo de detecção da Meta
- **Silencioso:** o grupo não fica poluído com mensagens de confirmação
- **Rastreável:** toda ação fica registrada no diário do Obsidian

Se quiser confirmação, é possível habilitar em grupos específicos quando a Evolution API estiver configurada.

---

## Casos de uso por projeto

### K2Con — Gestão de desenvolvimento
```
"task: corrigir SQL injection no módulo financeiro, prioridade crítica"
"decisão: vamos adiar o módulo contabilidade para v1.1"
"reunião: 25/04 16h — review do módulo CRM com time de devs"
"status: 33 módulos implementados, bugs P0 sendo corrigidos"
```

### Gestão EG — Financeiro multi-empresa
```
"lançamento: despesa R$2.800 Allp Fit categoria operacional vence 05/05"
"task: enviar DRE de março para todos os clientes até 30/04"
"nota: Contabilidade Exata pediu revisão do relatório de impostos"
```

### EG Build — Construção civil EUA
```
"task: integrar módulo Buildertrend com QuickBooks até 15/05"
"lançamento: receita $5.400 contratante ABC projeto Miami"
"decisão: usar SINAPI para orçamentos de obras residenciais"
```

### RODAG — Distribuidora diesel
```
"task: criar campanha B2B para rede de postos região Sul"
"nota: cliente Posto Alfa pediu proposta de automação CRM"
"reunião: 28/04 — onboarding EG OS com diretor RODAG"
```

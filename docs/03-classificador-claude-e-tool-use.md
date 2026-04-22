# Classificador Claude e Tool Use — Como funciona

**Projeto:** Integrador EG | **Atualizado:** Abril 2026

---

## Por que tool_use nativo (não JSON)

Na versão anterior, o Claude retornava um JSON em texto que o sistema tentava parsear. Isso causava:
- Falhas quando o Claude adicionava texto antes ou depois do JSON
- Erros silenciosos quando campos estavam faltando ou com nomes errados
- Necessidade de validação extensa do output

Com **tool_use nativo da Anthropic API**, o Claude chama diretamente a ferramenta correspondente à ação detectada. Não há JSON para parsear — o Claude preenche os campos da ferramenta como parâmetros estruturados, e a API garante o tipo correto de cada campo.

---

## Como o Claude classifica uma mensagem

**Entrada:**
```
Grupo: gestao-eg
Projeto: Gestão EG
Remetente: Luiz
Data/Hora: 2026-04-22 14:30

Mensagem:
preciso criar uma task de revisar o contrato do K2Con até sexta-feira, prioridade alta
```

**O Claude faz um tool call:**
```json
{
  "type": "tool_use",
  "id": "toolu_01XYZ",
  "name": "criar_task",
  "input": {
    "projeto": "Gestão EG",
    "conteudo_formatado": "## Task\n\n- [ ] Revisar contrato K2Con\n  - **Prazo:** sexta-feira\n  - **Remetente:** Luiz\n  - **Data:** 2026-04-22",
    "resumo_confirmacao": "Task criada: revisar contrato K2Con até sexta ✅",
    "prioridade": "alta",
    "idioma_detectado": "pt"
  }
}
```

**O sistema converte para ClassificacaoResult:**
- `acao`: AcaoTipo.CRIAR_TASK
- `projeto`: "Gestão EG"
- `conteudo_formatado`: markdown formatado
- `prioridade`: Prioridade.ALTA
- `resumo_confirmacao`: texto de confirmação
- `tool_use_id`: "toolu_01XYZ" (preservado para histórico multi-turn)

---

## As 13 ferramentas disponíveis

### Ferramentas de gestão (Obsidian)

**criar_nota** — Registra observação ou informação genérica
- Campos: projeto, conteudo_formatado, resumo_confirmacao, prioridade, idioma_detectado

**criar_reuniao** — Registra reunião com data/hora/pauta
- Campos: mesmo padrão base

**criar_task** — Cria tarefa com ou sem prazo e responsável
- Campos: mesmo padrão base

**registrar_decisao** — Documenta decisão tomada pela equipe
- Campos: mesmo padrão base

**atualizar_status** — Atualiza status de projeto ou tarefa existente
- Campos: mesmo padrão base

**criar_daily** — Registra diário do dia com atualizações de progresso
- Campos: mesmo padrão base

**consultar_tasks** — Consulta tasks pendentes (só leitura, não escreve)
- Campos: projeto, resumo_confirmacao

### Ferramentas financeiras

**registrar_lancamento** — Registra lançamento financeiro
- Campos base + valor (number), tipo ("receita"/"despesa"), categoria, fornecedor, data_vencimento

### Ferramentas de e-mail

**enviar_email** — Redige e envia novo e-mail
- Campos base + email_para, email_assunto, email_corpo, email_tipo, email_cc, email_bcc

**responder_email** — Responde a e-mail recebido
- Campos base + email_para, email_assunto, email_corpo, email_message_id, email_cc

**encaminhar_email** — Encaminha e-mail existente
- Campos base + email_para, email_assunto, email_corpo, email_message_id

**criar_rascunho** — Salva rascunho de e-mail no Obsidian (sem enviar)
- Campos base + email_para, email_assunto, email_corpo, email_tipo

### Controle de fluxo

**pedir_esclarecimento** — Usado quando mensagem é ambígua ou faltam dados essenciais
- Campos: projeto, pergunta (texto da pergunta para o usuário)
- Não escreve nada no Obsidian — apenas sinaliza que precisa de mais informação

---

## Prompt caching (redução de custo)

O sistema usa `cache_control: {"type": "ephemeral"}` nos blocos de system:

**Bloco 1 (sempre cacheado):** instruções estáticas do classificador
- O que é cada ferramenta
- Regras de idioma, prioridade, formatação
- Comportamento para mensagens ambíguas

**Bloco 2 (cacheado quando presente):** DNA narrativo do projeto
- Lido do Obsidian: `01 - Projetos/{projeto}.md`
- Contexto específico do projeto (o que é, quem são os envolvidos, linguagem usada)
- Permite respostas mais precisas e contextualizadas

**Benefício:** em uma conversa de múltiplos turnos no mesmo grupo, as instruções ficam em cache por 5 minutos. Cada mensagem subsequente só paga pelo contexto novo.

---

## Histórico multi-turn (HistoricoConversa)

O sistema mantém histórico por grupo no formato exato que a Anthropic API exige para multi-turn com tool_use:

```python
# Estrutura de um turno completo (3 blocos)
[
    # 1. Mensagem do usuário
    {"role": "user", "content": "criar task de revisar contrato"},

    # 2. Resposta do assistente (tool call)
    {"role": "assistant", "content": [{
        "type": "tool_use",
        "id": "toolu_01XYZ",
        "name": "criar_task",
        "input": {"projeto": "Gestão EG", ...}
    }]},

    # 3. Resultado da ferramenta
    {"role": "user", "content": [{
        "type": "tool_result",
        "tool_use_id": "toolu_01XYZ",
        "content": "registrado com sucesso"
    }]}
]
```

**Isso permite que o Claude entenda:**
- "adiciona mais uma task igual à anterior"
- "aquele projeto que falamos"
- "atualiza o status daquilo que criei agora pouco"

**Configurações do histórico:**
- TTL: 2 horas de inatividade (limpa automaticamente)
- Máximo: 8 pares de turnos (24 blocos)
- Storage: memória (não persiste entre restarts do servidor)
- Truncamento: sempre em múltiplos de 3 (mantém integridade da estrutura)

---

## Tratamento de mensagens ambíguas

Quando o Claude usa `pedir_esclarecimento`:

```json
{
  "name": "pedir_esclarecimento",
  "input": {
    "projeto": "Gestão EG",
    "pergunta": "Você quer criar uma task ou registrar uma reunião? Preciso de mais detalhes sobre o que aconteceu."
  }
}
```

O sistema:
1. Marca `requer_esclarecimento: True`
2. Não escreve nada no Obsidian
3. Registra no histórico a pergunta (para que na próxima mensagem o Claude tenha contexto)
4. Opcionalmente envia a pergunta de volta ao grupo

---

## Fallback de segurança

Se nenhum tool call for retornado (o que não deveria acontecer com `tool_choice: {"type": "any"}`):

```python
return ClassificacaoResult(
    acao=AcaoTipo.AMBIGUA,
    projeto=projeto,
    requer_esclarecimento=True,
    pergunta_esclarecimento="Não entendi bem. Pode detalhar?",
    resumo_confirmacao="Não entendi bem. Pode detalhar?",
)
```

O sistema nunca crasha por falta de tool call — sempre retorna um resultado utilizável.

---

## Configuração do modelo

```python
MODEL = "claude-haiku-4-5-20251001"  # rápido e barato para classificação
MAX_TOKENS = 1024  # tool calls precisam de mais tokens que plain JSON
```

**Nota:** o código usa "haiku" como modelo padrão para classificação rápida. Para casos que precisam de mais raciocínio (lançamentos financeiros complexos, emails), pode ser configurado para Sonnet.

---

## Exemplo completo de classificação de lançamento financeiro

**Mensagem:**
```
paguei $1500 para o fornecedor ABC pela impressão dos flyers do MKT, vence dia 30
```

**Tool call gerado pelo Claude:**
```json
{
  "name": "registrar_lancamento",
  "input": {
    "projeto": "MKT EG",
    "conteudo_formatado": "## Lançamento Financeiro\n\n**Tipo:** Despesa\n**Valor:** R$ 1.500,00\n**Fornecedor:** ABC\n**Categoria:** Marketing\n**Descrição:** Impressão de flyers\n**Vencimento:** 2026-04-30",
    "resumo_confirmacao": "Despesa de R$ 1.500 com ABC registrada 💰",
    "prioridade": "media",
    "idioma_detectado": "pt",
    "valor": 1500.00,
    "tipo": "despesa",
    "categoria": "marketing",
    "fornecedor": "ABC",
    "data_vencimento": "2026-04-30"
  }
}
```

**Campos extraídos no ClassificacaoResult:**
- `lancamento_valor`: 1500.0
- `lancamento_tipo`: "despesa"
- `lancamento_categoria`: "marketing"
- `lancamento_fornecedor`: "ABC"
- `lancamento_data_vencimento`: "2026-04-30"

Esses campos são usados pelo webhook para registrar também na plataforma financeira integrada (via `app_client.registrar_lancamento()`).

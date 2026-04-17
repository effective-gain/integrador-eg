# CLAUDE.md — WhatsApp OS

## Objetivo do projeto
Sistema onde mensagens (áudio ou texto) enviadas em grupos WhatsApp por projeto são interpretadas pelo Claude, executadas no Obsidian e confirmadas de volta no WhatsApp.

## Número WhatsApp
**+55 31 97224-4045** — número principal do Luiz (Evolution API)

## Fluxo completo
```
WhatsApp grupo (áudio/texto)
    → Evolution API webhook (+55 31 97224-4045)
    → n8n (orquestra)
    → se áudio: OpenAI Whisper (transcreve)
    → Claude API Sonnet 4.6 (classifica intenção → JSON)
    → Obsidian REST API porta 27124 (executa no vault)
    → WhatsApp (confirma ação no grupo)
```

## Stack
| Componente | Detalhe | Status |
|-----------|---------|--------|
| Evolution API | WhatsApp · +55 31 97224-4045 | A configurar |
| n8n | Self-hosted Easypanel (Hostinger) | Ativo |
| OpenAI Whisper | Transcrição de áudio | A integrar |
| Claude API Sonnet 4.6 | Classificador de intenção | Ativo |
| Obsidian REST API | `https://127.0.0.1:27124` | Ativo |
| obsidian_bridge.py | `C:\Users\user\Obsidian\` | Ativo |

## Obsidian — Acesso direto
**API key:** definida em `.env` como `OBSIDIAN_API_KEY` (nunca commitar)
**Base URL:** `https://127.0.0.1:27124`
**Vault:** `C:\Users\user\Documents\Effective Gain`
**Bridge:** `cd C:\Users\user\Obsidian && python obsidian_bridge.py [comando]`

## Grupos WhatsApp → Projetos
| Grupo WhatsApp | Projeto | Nota Obsidian | Notebook |
|---------------|---------|---------------|---------|
| K2Con | K2Con | `01 - Projetos/K2Con.md` | `72edea74` |
| EG Food | EG Food | `01 - Projetos/EG Food.md` | `d5eb240a` |
| Gestao EG | Gestao EG | `01 - Projetos/Gestao EG.md` | `06d696cd` |
| MKT EG | MKT EG | `01 - Projetos/MKT EG.md` | `0ebd3fd5` |
| Quickbooks | Quickbooks WhatsApp | `01 - Projetos/Quickbooks WhatsApp.md` | `2a5a0210` |
| EG Geral | — | `04 - Inbox/` | `baaa9a8a` |

## Ações suportadas pelo classificador
```json
{
  "acao": "criar_nota|criar_reuniao|criar_task|registrar_decisao|atualizar_status|consultar_tasks|registrar_lancamento|criar_daily",
  "projeto": "k2con|eg_food|gestao_eg|mkt_eg|quickbooks|geral",
  "conteudo": "texto extraído da mensagem",
  "prioridade": "alta|media|baixa"
}
```

## Workflows n8n (ordem de execução)
| # | Nome | Arquivo | Função |
|---|------|---------|--------|
| 1 | WA_RECEPTOR | `workflows/WA_RECEPTOR.json` | Webhook Evolution API → identifica grupo |
| 2 | WA_WHISPER | `workflows/WA_WHISPER.json` | Áudio → Whisper → texto |
| 3 | WA_CLASSIFIER | `workflows/WA_CLASSIFIER.json` | Texto → Claude API → JSON de ação |
| 4 | WA_EXECUTOR | `workflows/WA_EXECUTOR.json` | JSON → Obsidian REST API |
| 5 | WA_RESPONDER | `workflows/WA_RESPONDER.json` | Resultado → resposta no grupo |

## Prompts Claude
- `prompts/classifier.md` — prompt do classificador de intenção
- `prompts/responder.md` — prompt de resposta para o WhatsApp

## Scripts utilitários
- `scripts/test_obsidian.py` — testa conexão com Obsidian REST API
- `scripts/test_classifier.py` — testa classificador Claude com mensagens de exemplo
- `scripts/test_flow.py` — simula fluxo completo sem WhatsApp

## Regras de operação
- Nomenclatura n8n: `WA_[PROJETO]_[ACAO]`
- Todo workflow documentado no Notion antes de subir para produção
- Self-healing ativo em todos os workflows
- Dados sensíveis nunca em logs
- Testar sempre com `scripts/test_flow.py` antes de ativar nos grupos reais
- Número WhatsApp: +55 31 97224-4045

## Próximos passos (executar nesta ordem)
- [ ] 1. Configurar Evolution API + conectar +55 31 97224-4045
- [ ] 2. Importar e ativar WA_RECEPTOR no n8n
- [ ] 3. Integrar Whisper — testar com áudio de exemplo
- [ ] 4. Testar prompt classifier com `scripts/test_classifier.py`
- [ ] 5. Conectar Obsidian REST API — testar com `scripts/test_obsidian.py`
- [ ] 6. Rodar `scripts/test_flow.py` ponta a ponta
- [ ] 7. Ativar em grupo de teste (EG Geral)
- [ ] 8. Expandir para todos os grupos por projeto

## Skills a usar
- `n8n-skills` — construção dos workflows
- `crm-whatsapp-skills` — integração Evolution API + WhatsApp
- `self-healing` — recuperação automática de falhas nos workflows
- `researcher` — documentação de cada etapa no Notion

## Referências do ecossistema
- EG OS: `C:\Users\user\Desktop\GitHub - Effective Gain\Projetos no Claude\eg_os\CLAUDE.md`
- Obsidian vault: `C:\Users\user\Documents\Effective Gain`
- n8n: Easypanel (Hostinger)
- Notion: fonte de verdade — documentar workflows antes de subir

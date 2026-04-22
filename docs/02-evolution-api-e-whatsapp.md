# Evolution API e WhatsApp — Integração Detalhada

**Projeto:** Integrador EG | **Atualizado:** Abril 2026

---

## O que é a Evolution API

A Evolution API é uma camada de acesso ao WhatsApp que roda self-hosted. Ela conecta um número de WhatsApp ao sistema e expõe uma API REST para:
- Receber mensagens via webhook (o Integrador usa esta parte)
- Enviar mensagens de volta (o Integrador usa de forma opcional)

**Número operado:** +55 31 97224-4045 (número principal do Luiz/EG)

**Importante:** a Evolution API opera via sessão do WhatsApp Web — não usa a API oficial Meta. Isso significa que o número precisa ficar conectado como um telefone normal usando WhatsApp Web. A Meta não consegue distinguir isso de um usuário real.

---

## Como o webhook funciona

Quando uma mensagem chega no WhatsApp, a Evolution API faz um POST automático para o endpoint do Integrador:

```
POST https://[url-do-integrador]/webhook/whatsapp
Headers: x-api-key: [WEBHOOK_SECRET]
Content-Type: application/json
```

**Payload de exemplo (mensagem de texto):**

```json
{
  "data": {
    "key": {
      "remoteJid": "120363000000@g.us",
      "fromMe": false,
      "participant": "5531999990000@s.whatsapp.net"
    },
    "pushName": "Luiz",
    "message": {
      "conversation": "criar task: revisar contrato K2Con até sexta"
    }
  },
  "groupMetadata": {
    "subject": "k2con"
  }
}
```

**Payload de exemplo (mensagem de áudio):**

```json
{
  "data": {
    "key": {
      "remoteJid": "120363000000@g.us",
      "fromMe": false,
      "participant": "5531999990000@s.whatsapp.net"
    },
    "pushName": "Luiz",
    "message": {
      "audioMessage": {
        "url": "https://mmg.whatsapp.net/audio.ogg",
        "mimetype": "audio/ogg"
      }
    }
  },
  "groupMetadata": {
    "subject": "gestao-eg"
  }
}
```

---

## Como o Integrador parseia o webhook

O parsing é feito por `WhatsAppClient.parsear_webhook()` em `src/whatsapp.py`.

**Regras de parsing:**

| Campo | Origem no payload | Descrição |
|-------|-------------------|-----------|
| grupo_id | data.key.remoteJid | ID único do grupo WhatsApp |
| grupo_nome | groupMetadata.subject | Nome do grupo (usado para mapear projeto) |
| remetente | data.key.participant | Número do remetente |
| conteudo | data.message.conversation | Texto da mensagem |
| tipo_original | detectado automaticamente | "text", "audio", "image", "document" |
| arquivo_url | data.message.audioMessage.url | URL do arquivo (se houver) |

**Mensagens ignoradas automaticamente:**
- `fromMe: true` — mensagem enviada pelo próprio bot (evita loop)
- `remoteJid` terminando em `@s.whatsapp.net` — DM (não é grupo)
- Payload sem `groupMetadata` — não é grupo
- Payload malformado — retorna `None`, endpoint responde 200 com `{"status": "ignored"}`

---

## Modo de operação: passivo (só leitura)

O Integrador opera em **modo passivo** — ele recebe mensagens e executa ações, mas **não precisa enviar resposta de volta**.

Isso é importante porque:
- Enviar mensagens programaticamente é o que a Meta monitora e pode banir
- Receber mensagens é comportamento normal de qualquer WhatsApp Web
- A confirmação da ação vai para o Obsidian (diário), não de volta ao grupo

Se a variável `EVOLUTION_API_URL` estiver configurada, o Integrador PODE enviar confirmações. Se não estiver, opera em modo silencioso — executa e registra, sem responder.

---

## Controle do bot por grupo (BotStatus)

Qualquer mensagem enviada no grupo pode ser um **comando de controle**. O sistema verifica ANTES de qualquer processamento:

| Comando | Efeito | Resposta |
|---------|--------|----------|
| `/pausar` | Pausa indefinidamente | "⏸️ Bot pausado indefinidamente" |
| `/pausar 2h` | Pausa por 2 horas | "⏸️ Bot pausado por *2h*" |
| `/pausar 30m` | Pausa por 30 minutos | "⏸️ Bot pausado por *30m*" |
| `/pausar 1h30m` | Pausa por 1h30 | "⏸️ Bot pausado por *1h30m*" |
| `/ativar` | Reativa o bot | "▶️ Bot reativado!" |
| `/status` | Mostra estado atual | "✅ Bot ativo..." ou "⏸️ Bot pausado até..." |
| `/botstatus` | Alias de /status | idem |

**Comportamento quando pausado:**
- Comandos de controle (`/ativar`, `/status`) ainda funcionam
- Mensagens normais são ignoradas silenciosamente
- O grupo não recebe nenhum aviso de que a mensagem foi ignorada
- Quando o TTL expira, o bot reativa automaticamente sem notificar o grupo

**Persistência:** o estado de pausa é salvo em Postgres (não se perde com restart do servidor).

---

## Fluxo de processamento de áudio

Quando o tipo é `audioMessage`:

1. `whatsapp.download_audio(url)` — baixa o arquivo .ogg da URL do WhatsApp
2. `transcriber.transcrever(bytes_do_audio)` — envia para OpenAI Whisper
3. Retorna texto transcrito em português
4. O texto transcrito é tratado igual a uma mensagem de texto normal
5. O tipo original (`audio`) é preservado nos metadados para o diário

**Fallback:** se Whisper não estiver configurado (`OPENAI_API_KEY` ausente), o bot avisa que transcrição não está disponível.

---

## Suporte a tipos de mensagem

| Tipo | Campo no payload | Status | Tratamento |
|------|-----------------|--------|------------|
| Texto | message.conversation | ✅ Suportado | Processado diretamente |
| Áudio | message.audioMessage | ✅ Suportado | Transcrito via Whisper |
| Imagem | message.imageMessage | ⬜ Planejado | Não implementado ainda |
| Documento | message.documentMessage | ⬜ Planejado | Não implementado ainda |
| Sticker | message.stickerMessage | ⬜ Ignorado | Não processado |

---

## Autenticação do webhook

Todo webhook recebido passa pela verificação de `x-api-key`:

```python
async def _verificar_api_key(api_key: str | None = Security(_api_key_header)):
    secret = await _get_webhook_secret()
    if not secret:
        return  # dev mode: sem secret configurado, aceita tudo
    if api_key != secret:
        raise HTTPException(status_code=403, detail="Acesso negado")
```

**Hierarquia do secret:**
1. Banco de dados Postgres (configurações dinâmicas)
2. Variável de ambiente `WEBHOOK_SECRET` no `.env`
3. Se nenhum dos dois, aceita qualquer requisição (modo dev)

Na Evolution API, configure este header em "Webhook Settings" → "Headers" → `x-api-key: [seu-secret]`.

---

## Configuração da Evolution API

### Variáveis necessárias no .env

```env
EVOLUTION_API_URL=https://[sua-url-easypanel]/
EVOLUTION_INSTANCE=integrador-eg
EVOLUTION_API_KEY=[chave-da-evolution-api]
WEBHOOK_SECRET=[segredo-compartilhado]
```

### Configuração do webhook na Evolution API

```
Webhook URL: https://[url-do-integrador]/webhook/whatsapp
Método: POST
Headers: x-api-key: [WEBHOOK_SECRET]
Eventos: MESSAGES_UPSERT (mensagens recebidas)
```

### Teste de conexão

```bash
# Verifica se o Integrador está recebendo webhooks
curl -X POST https://[url]/webhook/whatsapp \
  -H "x-api-key: [secret]" \
  -H "Content-Type: application/json" \
  -d '{"data":{"key":{"remoteJid":"test@g.us","fromMe":false},"message":{"conversation":"teste"}},"groupMetadata":{"subject":"gestao-eg"}}'
```

---

## Relação com a API Oficial Meta (WhatsApp Business API)

A Evolution API NÃO é a API oficial Meta. Diferenças:

| Critério | Evolution API | API Oficial Meta |
|----------|--------------|-----------------|
| Aprovação Meta | Não necessária | Necessária (semanas) |
| Custo por mensagem | Nenhum | Pago por template |
| Envio de mensagens | Sim (via sessão) | Sim (via API) |
| Receber mensagens | Sim (webhook) | Sim (webhook) |
| Risco de ban | Baixo em modo passivo | Nenhum |
| Setup | Simples | Complexo |

**Para o modelo atual (modo passivo/só leitura):** a Evolution API é suficiente e segura. O risco de ban da Meta é praticamente zero quando o número só recebe mensagens e não envia automações em massa.

**Quando migrar para API oficial:** se o produto escalar para envio de mensagens em massa ou templates para clientes externos que não fazem parte dos grupos.

import pytest
from src.whatsapp import WhatsAppClient
from src.models import MensagemEntrada


def test_parsear_mensagem_texto_de_grupo():
    payload = {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": False,
                "participant": "5531999999999@s.whatsapp.net",
            },
            "pushName": "Luiz",
            "message": {"conversation": "preciso registrar uma nota"},
        },
        "groupMetadata": {"subject": "gestao-eg"},
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is not None
    assert msg.conteudo == "preciso registrar uma nota"
    assert msg.tipo_original == "text"
    assert msg.grupo_nome == "gestao-eg"
    assert msg.remetente == "Luiz"


def test_ignorar_mensagem_do_proprio_bot():
    payload = {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": True,
            },
            "message": {"conversation": "mensagem enviada pelo bot"},
        }
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is None


def test_ignorar_mensagem_de_dm():
    payload = {
        "data": {
            "key": {
                "remoteJid": "5531999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Alguém",
            "message": {"conversation": "oi"},
        }
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is None


def test_parsear_mensagem_audio():
    payload = {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": False,
                "participant": "5531@s.whatsapp.net",
            },
            "pushName": "Luiz",
            "message": {
                "audioMessage": {
                    "url": "https://mmg.whatsapp.net/audio.ogg",
                    "mimetype": "audio/ogg",
                }
            },
        },
        "groupMetadata": {"subject": "k2con"},
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is not None
    assert msg.tipo_original == "audio"
    assert msg.conteudo == ""  # será transcrito depois
    assert msg.arquivo_url == "https://mmg.whatsapp.net/audio.ogg"


def test_parsear_mensagem_documento_com_caption():
    payload = {
        "data": {
            "key": {
                "remoteJid": "120363000000@g.us",
                "fromMe": False,
                "participant": "5531@s.whatsapp.net",
            },
            "pushName": "Fornecedor",
            "message": {
                "documentMessage": {
                    "caption": "invoice dezembro",
                    "fileName": "invoice.pdf",
                }
            },
        },
        "groupMetadata": {"subject": "beef-smash"},
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is not None
    assert msg.tipo_original == "document"
    assert msg.conteudo == "invoice dezembro"


def test_parsear_payload_corrompido_retorna_none():
    msg = WhatsAppClient.parsear_webhook({})
    assert msg is None


def test_parsear_tipo_nao_suportado_retorna_none():
    payload = {
        "data": {
            "key": {"remoteJid": "120363000000@g.us", "fromMe": False},
            "message": {"reactionMessage": {"text": "👍"}},
        }
    }
    msg = WhatsAppClient.parsear_webhook(payload)
    assert msg is None

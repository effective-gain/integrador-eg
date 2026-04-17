"""Testa Transcriber (Whisper) sem chamada real à API OpenAI."""
import pytest
import respx
import httpx

from src.transcriber import Transcriber, TranscritorError, WHISPER_URL


def make_transcriber():
    return Transcriber(api_key="sk-test")


@pytest.mark.asyncio
@respx.mock
async def test_transcrever_sucesso():
    respx.post(WHISPER_URL).mock(return_value=httpx.Response(200, json={"text": "reunião confirmada para sexta"}))
    transcriber = make_transcriber()
    texto = await transcriber.transcrever(b"fake-audio-bytes")
    assert texto == "reunião confirmada para sexta"


@pytest.mark.asyncio
@respx.mock
async def test_transcrever_erro_api():
    respx.post(WHISPER_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
    transcriber = make_transcriber()
    with pytest.raises(TranscritorError, match="401"):
        await transcriber.transcrever(b"fake-audio-bytes")


@pytest.mark.asyncio
async def test_transcrever_audio_vazio():
    transcriber = make_transcriber()
    with pytest.raises(TranscritorError, match="vazio"):
        await transcriber.transcrever(b"")


@pytest.mark.asyncio
@respx.mock
async def test_transcrever_timeout():
    respx.post(WHISPER_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    transcriber = make_transcriber()
    with pytest.raises(TranscritorError, match="Timeout"):
        await transcriber.transcrever(b"fake")


@pytest.mark.asyncio
@respx.mock
async def test_transcrever_offline():
    respx.post(WHISPER_URL).mock(side_effect=httpx.ConnectError("refused"))
    transcriber = make_transcriber()
    with pytest.raises(TranscritorError, match="conectar"):
        await transcriber.transcrever(b"fake")


@pytest.mark.asyncio
@respx.mock
async def test_transcrever_texto_vazio_da_api():
    respx.post(WHISPER_URL).mock(return_value=httpx.Response(200, json={"text": ""}))
    transcriber = make_transcriber()
    with pytest.raises(TranscritorError, match="vazio"):
        await transcriber.transcrever(b"fake")

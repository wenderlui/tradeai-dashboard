"""Narração da análise com edge-tts (gera MP3 em memória)."""

from __future__ import annotations

import asyncio
import re
import threading

VOZ_PADRAO = "pt-BR-FranciscaNeural"
LIMITE_CARACTERES = 900


def limpar_para_fala(texto: str) -> str:
    """Remove Markdown e emojis para a narração ficar natural."""
    t = re.sub(r"[*_`#>|]", "", texto)
    t = re.sub(r"^\s*-\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > LIMITE_CARACTERES:
        t = t[:LIMITE_CARACTERES].rsplit(" ", 1)[0] + "."
    return t


async def _sintetizar(texto: str, voz: str) -> bytes:
    import edge_tts

    partes = bytearray()
    async for chunk in edge_tts.Communicate(texto, voz).stream():
        if chunk.get("type") == "audio":
            partes.extend(chunk["data"])
    return bytes(partes)


def _rodar(coro):
    """Executa a corrotina mesmo se já houver um event loop rodando nesta thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    resultado: dict = {}

    def alvo():
        try:
            resultado["valor"] = asyncio.run(coro)
        except BaseException as exc:  # repassa para a thread principal
            resultado["erro"] = exc

    t = threading.Thread(target=alvo)
    t.start()
    t.join()
    if "erro" in resultado:
        raise resultado["erro"]
    return resultado["valor"]


def gerar_audio(texto: str, voz: str = VOZ_PADRAO) -> bytes | None:
    texto = limpar_para_fala(texto)
    if not texto:
        return None
    audio = _rodar(_sintetizar(texto, voz))
    return audio or None

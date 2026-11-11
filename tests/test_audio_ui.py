import asyncio

import pytest

from tradeai import audio, ui
from tradeai.market import dados_demo


def test_limpar_para_fala():
    texto = "**Veredito:** COMPRA 🚀\n- RSI em _30_\n\n\n# Título"
    limpo = audio.limpar_para_fala(texto)
    assert "*" not in limpo and "_" not in limpo and "#" not in limpo and "🚀" not in limpo
    assert "Veredito: COMPRA" in limpo and "RSI em 30" in limpo


def test_limpar_para_fala_limita_tamanho():
    assert len(audio.limpar_para_fala("palavra " * 500)) <= audio.LIMITE_CARACTERES + 1


def test_gerar_audio_texto_vazio():
    assert audio.gerar_audio("** ** 🚀") is None


def test_gerar_audio_usa_sintetizador(monkeypatch):
    async def fake(texto, voz):
        return f"{voz}:{texto}".encode()

    monkeypatch.setattr(audio, "_sintetizar", fake)
    assert audio.gerar_audio("**Olá**") == f"{audio.VOZ_PADRAO}:Olá".encode()


def test_rodar_funciona_dentro_de_event_loop(monkeypatch):
    async def fake(texto, voz):
        return b"mp3"

    monkeypatch.setattr(audio, "_sintetizar", fake)

    async def dentro():
        return audio.gerar_audio("teste")

    assert asyncio.run(dentro()) == b"mp3"


def test_rodar_propaga_erro():
    async def quebra():
        raise RuntimeError("falhou")

    async def dentro():
        return audio._rodar(quebra())

    with pytest.raises(RuntimeError, match="falhou"):
        asyncio.run(dentro())


def test_card_escapa_html():
    html = ui.card("<b>x</b>", "<script>alert(1)</script>", "sub & cia", "ta-up")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "sub &amp; cia" in html


def test_card_barra_limitada():
    assert "width:100%" in ui.card("a", "b", barra=(250, "#fff"))
    assert "width:0%" in ui.card("a", "b", barra=(-5, "#fff"))


def test_cabecalho_escapa():
    h = ui.cabecalho("<x>/USDT", "15 min", "binance", "10:00", online=True)
    assert "&lt;x&gt;" in h and "Ao vivo" in h
    assert "Demonstração" in ui.cabecalho("BTC/USDT", "15 min", "demo", "10:00", online=False)


@pytest.mark.parametrize("v, classe", [(1, "ta-up"), (-1, "ta-down"), (0, "ta-neutral")])
def test_classe_tendencia(v, classe):
    assert ui.classe_tendencia(v) == classe


def test_cor_score():
    assert ui.cor_score(80) == ui.VERDE and ui.cor_score(20) == ui.VERMELHO and ui.cor_score(50) == ui.AMARELO


def test_tradingview_html():
    h = ui.tradingview_html("BTC/USDT", "4h", "GATEIO")
    assert '"symbol": "GATEIO:BTCUSDT"' in h and '"interval": "240"' in h


def test_grafico_indicadores():
    fig = ui.grafico_indicadores(dados_demo().df, "BTC/USDT")
    assert [t.name for t in fig.data] == ["BTC/USDT", "EMA 9", "EMA 21", "RSI 14"]

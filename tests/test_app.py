"""Testes de ponta a ponta da interface com o AppTest do Streamlit."""

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tradeai import audio
from tradeai.market import DadosIndisponiveis, MarketDataService, dados_demo

from .conftest import RAIZ

APP = str(RAIZ / "main.py")


@pytest.fixture(autouse=True)
def isolar(monkeypatch):
    st.cache_data.clear()
    st.cache_resource.clear()

    async def sem_rede(texto, voz):
        return b"mp3-falso"

    monkeypatch.setattr(audio, "_sintetizar", sem_rede)
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def abrir(monkeypatch=None, demo=True):
    if monkeypatch and demo:
        monkeypatch.setenv("TRADEAI_DEMO", "1")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def textos(at):
    return " ".join(m.value for m in at.markdown)


def test_abre_em_modo_demo(monkeypatch):
    at = abrir(monkeypatch)
    conteudo = textos(at)
    assert "TradeAI" in conteudo and "Score técnico" in conteudo and "RSI (14)" in conteudo
    assert any("simulados" in w.value for w in at.warning)


def test_gerar_analise_offline_e_historico(monkeypatch):
    at = abrir(monkeypatch)
    botao = next(b for b in at.button if b.label == "Gerar análise")
    botao.click().run()
    assert not at.exception
    hist = at.session_state["historico"]
    assert len(hist) == 1 and hist[0]["offline"] and "Veredito" in hist[0]["texto"]

    next(b for b in at.button if b.label == "Gerar análise").click().run()
    assert len(at.session_state["historico"]) == 2

    next(b for b in at.button if b.label == "Limpar histórico de análises").click().run()
    assert at.session_state["historico"] == []


def test_troca_de_ativo_e_tempo(monkeypatch):
    at = abrir(monkeypatch)
    at.sidebar.selectbox[0].select("Dogecoin (DOGE)").run()
    assert not at.exception
    assert "Preço DOGE" in textos(at)


def test_par_personalizado_invalido(monkeypatch):
    at = abrir(monkeypatch)
    at.sidebar.selectbox[0].select("Outro par…").run()
    at.sidebar.text_input[0].input("   ").run()
    assert any("Informe um símbolo" in e.value for e in at.error)


def test_par_personalizado_valido(monkeypatch):
    at = abrir(monkeypatch)
    at.sidebar.selectbox[0].select("Outro par…").run()
    at.sidebar.text_input[0].input("pepeusdt").run()
    assert not at.exception and "PEPE/USDT" in textos(at)


def test_dados_reais_com_corretora_falsa(monkeypatch):
    monkeypatch.setattr(MarketDataService, "snapshot", lambda self, s, tf: dados_demo(s, tf))
    at = abrir(demo=False)
    assert "Ao vivo" in textos(at)
    assert not any("simulados" in w.value for w in at.warning)


def test_mercado_indisponivel_mostra_erro_amigavel(monkeypatch):
    def falha(self, s, tf):
        raise DadosIndisponiveis("Não foi possível obter dados de BTC/USDT.")

    monkeypatch.setattr(MarketDataService, "snapshot", falha)
    at = abrir(demo=False)
    assert any("Não foi possível carregar o mercado" in e.value for e in at.error)
    assert any(b.label == "Tentar novamente" for b in at.button)

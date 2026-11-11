"""TradeAI Pro — dashboard de análise técnica de criptomoedas com IA.

Execute com:  streamlit run main.py
"""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components
from dotenv import find_dotenv, load_dotenv

from tradeai import ui
from tradeai.ai import AVISO_LEGAL, AIService
from tradeai.audio import gerar_audio
from tradeai.indicators import ativo_base, formatar_preco, normalizar_simbolo, zona_rsi
from tradeai.market import TIMEFRAMES, DadosIndisponiveis, MarketDataService, Snapshot, dados_demo

load_dotenv(find_dotenv(usecwd=True))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # Windows sem tzdata
    FUSO = None

MOEDAS = {
    "Bitcoin (BTC)": "BTC/USDT",
    "Ethereum (ETH)": "ETH/USDT",
    "Solana (SOL)": "SOL/USDT",
    "BNB (BNB)": "BNB/USDT",
    "XRP (XRP)": "XRP/USDT",
    "Polygon (POL)": "POL/USDT",
    "Litecoin (LTC)": "LTC/USDT",
    "Dogecoin (DOGE)": "DOGE/USDT",
    "Polkadot (DOT)": "DOT/USDT",
    "Chainlink (LINK)": "LINK/USDT",
    "Cosmos (ATOM)": "ATOM/USDT",
    "Aave (AAVE)": "AAVE/USDT",
    "Uniswap (UNI)": "UNI/USDT",
}
OUTRO = "Outro par…"
TV_EXCHANGES = {
    "binance": "BINANCE",
    "gate": "GATEIO",
    "gateio": "GATEIO",
    "kucoin": "KUCOIN",
    "okx": "OKX",
    "bybit": "BYBIT",
}
MAX_HISTORICO = 10

st.set_page_config(page_title="TradeAI Pro", page_icon="📈", layout="wide", initial_sidebar_state="auto")
st.markdown(ui.CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- serviços
@st.cache_resource(show_spinner=False)
def servico_mercado() -> MarketDataService:
    return MarketDataService()


@st.cache_resource(show_spinner=False)
def servico_ia() -> AIService:
    return AIService()


@st.cache_data(ttl=30, show_spinner=False)
def carregar_snapshot(simbolo: str, timeframe: str, demo: bool) -> Snapshot:
    if demo:
        return dados_demo(simbolo, timeframe)
    return servico_mercado().snapshot(simbolo, timeframe)


def agora() -> datetime:
    return datetime.now(FUSO) if FUSO else datetime.now()


# ---------------------------------------------------------------- estado
st.session_state.setdefault("historico", [])

# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    moeda = st.selectbox("Ativo", list(MOEDAS) + [OUTRO], index=0)
    erro_simbolo = None
    if moeda == OUTRO:
        entrada = st.text_input("Par (ex.: PEPE, PEPEUSDT ou PEPE/USDT)", "PEPE/USDT")
        try:
            simbolo = normalizar_simbolo(entrada)
        except ValueError as exc:
            erro_simbolo = str(exc)
            simbolo = ""
    else:
        simbolo = MOEDAS[moeda]

    rotulo_tempo = (
        st.segmented_control("Tempo gráfico", list(TIMEFRAMES), default="15 min", selection_mode="single") or "15 min"
    )
    timeframe = TIMEFRAMES[rotulo_tempo]

    st.markdown("### 🔔 Preferências")
    narrar = st.toggle("Narrar análise em voz", value=True)
    auto_refresh = st.toggle("Atualizar preços a cada 60 s", value=False)
    demo = st.toggle(
        "Modo demonstração",
        value=os.getenv("TRADEAI_DEMO", "").lower() in ("1", "true", "sim"),
        help="Usa dados simulados. Útil sem internet ou para apresentações.",
    )

    st.divider()
    ia = servico_ia()
    if ia.configurada:
        st.success("Gemini conectado", icon="✅")
    else:
        st.info(
            "Sem chave do Gemini: a análise usa o modo matemático local. "
            "Configure `GEMINI_API_KEY` no `.env` ou em `.streamlit/secrets.toml`.",
            icon="ℹ️",
        )
    if st.button("Limpar histórico de análises", width="stretch"):
        st.session_state.historico = []

    st.caption("Dados: Binance, Gate, KuCoin, OKX, Bybit (via ccxt) · IA: Google Gemini")


if erro_simbolo:
    st.error(erro_simbolo)
    st.stop()


# ---------------------------------------------------------------- painel
@st.fragment(run_every=60 if auto_refresh else None)
def painel() -> None:
    try:
        snap = carregar_snapshot(simbolo, timeframe, demo)
    except DadosIndisponiveis as exc:
        st.markdown(
            ui.cabecalho(simbolo, rotulo_tempo, "—", agora().strftime("%H:%M:%S"), online=False), unsafe_allow_html=True
        )
        st.error(
            f"**Não foi possível carregar o mercado.** {exc}\n\n"
            "Verifique sua conexão e se o par existe. Você também pode ativar o **Modo demonstração** na barra lateral.",
            icon="🚫",
        )
        if st.button("Tentar novamente", type="primary"):
            carregar_snapshot.clear()
            st.rerun()
        return

    st.markdown(
        ui.cabecalho(snap.simbolo, rotulo_tempo, snap.exchange, agora().strftime("%d/%m %H:%M:%S"), online=not demo),
        unsafe_allow_html=True,
    )
    for aviso in snap.avisos:
        st.warning(aviso)
    if demo:
        st.warning("Modo demonstração ativo: os preços abaixo são **simulados**.", icon="🧪")

    # --- cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            ui.card(
                f"Preço {ativo_base(snap.simbolo)}",
                f"${formatar_preco(snap.preco)}",
                f"{snap.variacao:+.2f}% em {len(snap.df)} candles",
                ui.classe_tendencia(snap.variacao),
            ),
            unsafe_allow_html=True,
        )
    with c2:
        cor_rsi = ui.VERMELHO if snap.rsi > 70 else ui.VERDE if snap.rsi < 30 else ui.AMARELO
        st.markdown(
            ui.card("RSI (14)", f"{snap.rsi:.1f}", zona_rsi(snap.rsi), "", barra=(snap.rsi, cor_rsi)),
            unsafe_allow_html=True,
        )
    with c3:
        dist = (snap.preco - snap.ema21) / snap.ema21 * 100 if snap.ema21 else 0.0
        tendencia = "Alta" if snap.ema9 > snap.ema21 else "Baixa" if snap.ema9 < snap.ema21 else "Lateral"
        st.markdown(
            ui.card("Tendência (EMA 9/21)", tendencia, f"{dist:+.2f}% vs EMA21", ui.classe_tendencia(dist)),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            ui.card(
                "Score técnico",
                f"{snap.score.valor}/100",
                snap.score.rotulo,
                ui.classe_tendencia(snap.score.valor, 50),
                barra=(snap.score.valor, ui.cor_score(snap.score.valor)),
            ),
            unsafe_allow_html=True,
        )

    # --- IA
    st.markdown('<div class="ta-section">🧠 Análise inteligente</div>', unsafe_allow_html=True)
    col_acao, col_info = st.columns([1, 3], vertical_alignment="center")
    with col_acao:
        gerar = st.button("Gerar análise", type="primary", icon="✨", width="stretch")
    with col_info:
        st.caption(
            f"Considera preço, RSI, EMAs, máxima/mínima recentes e o score técnico de **{snap.simbolo}** em **{rotulo_tempo}**."
        )

    audio = None
    if gerar:
        with st.spinner("Analisando o mercado…"):
            analise = servico_ia().analisar(snap.para_prompt())
        st.session_state.historico.insert(
            0,
            {
                "texto": analise.texto,
                "modelo": analise.modelo,
                "offline": analise.offline,
                "simbolo": snap.simbolo,
                "tempo": rotulo_tempo,
                "hora": agora().strftime("%d/%m %H:%M"),
            },
        )
        del st.session_state.historico[MAX_HISTORICO:]
        if narrar:
            try:
                audio = gerar_audio(analise.texto)
            except Exception as exc:  # narração nunca deve derrubar o app
                logging.getLogger(__name__).warning("Falha na narração: %s", exc)
                st.toast("Não foi possível gerar a narração.", icon="🔇")

    historico = st.session_state.historico
    col_atual, col_hist = st.columns([3, 2])
    with col_atual:
        with st.container(border=True, height=330):
            if historico:
                atual = historico[0]
                origem = "Análise local" if atual["offline"] else f"Gemini · {atual['modelo']}"
                st.markdown(
                    '<div class="ta-ai-meta">'
                    + html.escape(f"{atual['simbolo']} · {atual['tempo']} · {atual['hora']} · {origem}")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(atual["texto"])
                st.caption(AVISO_LEGAL)
            else:
                st.markdown("#### Nenhuma análise ainda")
                st.caption("Clique em **Gerar análise** para receber um parecer sobre o ativo selecionado.")
        if audio:
            st.audio(audio, format="audio/mp3", autoplay=True)
    with col_hist:
        with st.container(border=True, height=330):
            st.markdown("**📜 Histórico**")
            if len(historico) <= 1:
                st.caption("As análises anteriores aparecem aqui.")
            for item in historico[1:]:
                with st.expander(f"{item['hora']} · {item['simbolo']} · {item['tempo']}"):
                    st.markdown(item["texto"])

    # --- gráficos
    st.markdown('<div class="ta-section">📊 Gráficos</div>', unsafe_allow_html=True)
    aba_tv, aba_ind = st.tabs(["TradingView", "Indicadores do app"])
    with aba_tv:
        components.html(
            ui.tradingview_html(snap.simbolo, timeframe, TV_EXCHANGES.get(snap.exchange, "BINANCE")),
            height=570,
        )
    with aba_ind:
        df = snap.df.copy()
        if FUSO:
            df["time"] = df["time"].dt.tz_convert(FUSO)
        st.plotly_chart(ui.grafico_indicadores(df, snap.simbolo), width="stretch", config={"displaylogo": False})

    with st.expander("ℹ️ Metodologia"):
        st.markdown(
            "- **RSI (14)** com suavização de Wilder; abaixo de 30 = sobrevenda, acima de 70 = sobrecompra.\n"
            "- **EMA 9 / EMA 21**: médias exponenciais; EMA9 acima da EMA21 indica tendência de alta.\n"
            "- **Score técnico (0–100)**: combina RSI, posição do preço frente à EMA21 e o cruzamento das médias. "
            "50 é neutro.\n"
            f"- Motivos do score atual: {'; '.join(snap.score.motivos) or '—'}.\n"
            "- **IA**: Google Gemini com rotação automática de modelos. Sem chave ou sem cota, "
            "o app usa uma análise matemática local."
        )


painel()

st.markdown(
    '<div class="ta-footer">TradeAI Pro · Conteúdo educativo, não constitui recomendação de investimento. '
    "Criptoativos são voláteis: opere com gestão de risco.</div>",
    unsafe_allow_html=True,
)

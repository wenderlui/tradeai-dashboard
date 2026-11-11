"""Componentes visuais (HTML/CSS e gráficos) do dashboard."""

from __future__ import annotations

import html
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

VERDE = "#16c784"
VERMELHO = "#ea3943"
AMARELO = "#f0b90b"
AZUL = "#3b82f6"
TEXTO_SUAVE = "#8b949e"

CSS = """
<style>
:root {
  --bg: #0b0e11; --surface: #12161c; --surface-2: #181d24; --border: #232a33;
  --text: #e6e8eb; --muted: #8b949e; --green: #16c784; --red: #ea3943; --yellow: #f0b90b;
}
.stApp { background: var(--bg); }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1440px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
#MainMenu, footer { visibility: hidden; }

.ta-header { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom: 1.2rem; }
.ta-brand { display:flex; align-items:center; gap:12px; }
.ta-logo { width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg, #16c784 0%, #0ea5e9 100%); font-weight:800; color:#0b0e11; font-size:18px; }
.ta-title { font-size:22px; font-weight:700; color:var(--text); line-height:1.1; }
.ta-subtitle { font-size:13px; color:var(--muted); }
.ta-badges { display:flex; gap:8px; flex-wrap:wrap; }
.ta-badge { font-size:12px; color:var(--muted); background:var(--surface); border:1px solid var(--border);
  padding:5px 10px; border-radius:999px; white-space:nowrap; }
.ta-badge b { color:var(--text); font-weight:600; }
.ta-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; vertical-align:middle; }

.ta-card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:16px 18px;
  height:100%; min-height:118px; transition:border-color .2s ease; }
.ta-card:hover { border-color:#334155; }
.ta-card-label { font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin-bottom:6px; }
.ta-card-value { font-size:26px; font-weight:700; color:var(--text); font-variant-numeric: tabular-nums; }
.ta-card-sub { font-size:13px; margin-top:4px; color:var(--muted); }
.ta-up { color:var(--green) !important; } .ta-down { color:var(--red) !important; } .ta-neutral { color:var(--yellow) !important; }
.ta-bar { height:6px; background:var(--surface-2); border-radius:999px; margin-top:10px; overflow:hidden; }
.ta-bar > span { display:block; height:100%; border-radius:999px; }

.ta-section { font-size:15px; font-weight:600; color:var(--text); margin: 1.4rem 0 .6rem; }
.ta-ai-meta { font-size:12px; color:var(--muted); margin-bottom:8px; }
.ta-footer { margin-top:2rem; padding-top:1rem; border-top:1px solid var(--border); color:var(--muted); font-size:12px; text-align:center; }

div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }
.stButton > button[kind="primary"] { background: var(--green); border-color: var(--green); color:#0b0e11; font-weight:700; }
.stButton > button[kind="primary"]:hover { filter: brightness(1.1); border-color: var(--green); color:#0b0e11; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
</style>
"""


def classe_tendencia(valor: float, neutro: float = 0.0) -> str:
    if valor > neutro:
        return "ta-up"
    if valor < neutro:
        return "ta-down"
    return "ta-neutral"


def cor_score(valor: int) -> str:
    if valor > 60:
        return VERDE
    if valor < 40:
        return VERMELHO
    return AMARELO


def card(rotulo: str, valor: str, sub: str = "", classe_sub: str = "", barra: tuple[float, str] | None = None) -> str:
    """Card de métrica. Todo texto é escapado para evitar injeção de HTML."""
    barra_html = '<div class="ta-bar" style="visibility:hidden"></div>'
    if barra is not None:
        pct, cor = barra
        pct = max(0.0, min(100.0, float(pct)))
        barra_html = f'<div class="ta-bar"><span style="width:{pct:.0f}%;background:{html.escape(cor)}"></span></div>'
    return (
        '<div class="ta-card">'
        f'<div class="ta-card-label">{html.escape(rotulo)}</div>'
        f'<div class="ta-card-value">{html.escape(valor)}</div>'
        f'<div class="ta-card-sub {html.escape(classe_sub)}">{html.escape(sub)}</div>'
        f"{barra_html}</div>"
    )


def cabecalho(simbolo: str, timeframe: str, exchange: str, atualizado: str, online: bool) -> str:
    cor = VERDE if online else AMARELO
    status = "Ao vivo" if online else "Demonstração"
    return f"""
<div class="ta-header">
  <div class="ta-brand">
    <div class="ta-logo">T</div>
    <div>
      <div class="ta-title">TradeAI <span style="color:{TEXTO_SUAVE};font-weight:500">Pro</span></div>
      <div class="ta-subtitle">Análise técnica de criptomoedas com IA</div>
    </div>
  </div>
  <div class="ta-badges">
    <span class="ta-badge"><span class="ta-dot" style="background:{cor}"></span><b>{html.escape(status)}</b></span>
    <span class="ta-badge">Par <b>{html.escape(simbolo)}</b></span>
    <span class="ta-badge">Tempo <b>{html.escape(timeframe)}</b></span>
    <span class="ta-badge">Fonte <b>{html.escape(exchange.capitalize())}</b></span>
    <span class="ta-badge">Atualizado <b>{html.escape(atualizado)}</b></span>
  </div>
</div>
"""


def grafico_indicadores(df: pd.DataFrame, simbolo: str) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=simbolo,
            increasing_line_color=VERDE,
            decreasing_line_color=VERMELHO,
            increasing_fillcolor=VERDE,
            decreasing_fillcolor=VERMELHO,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["ema9"], name="EMA 9", line=dict(color=AMARELO, width=1.4)), row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["ema21"], name="EMA 21", line=dict(color=AZUL, width=1.4)), row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["rsi"], name="RSI 14", line=dict(color="#a78bfa", width=1.4)), row=2, col=1
    )
    for nivel, cor in ((70, VERMELHO), (30, VERDE)):
        fig.add_hline(y=nivel, line=dict(color=cor, width=1, dash="dot"), row=2, col=1)

    grade = "rgba(139,148,158,0.12)"
    fig.update_layout(
        template="plotly_dark",
        height=560,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        font=dict(color="#c9d1d9"),
    )
    fig.update_xaxes(gridcolor=grade, showspikes=True, spikecolor=TEXTO_SUAVE, spikethickness=1)
    fig.update_yaxes(gridcolor=grade, side="right")
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    return fig


TV_INTERVALOS = {"5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240", "1d": "D"}


def tradingview_html(simbolo: str, timeframe: str, exchange: str = "BINANCE", altura: int = 560) -> str:
    par = simbolo.replace("/", "").upper()
    config = {
        "autosize": True,
        "symbol": f"{exchange.upper()}:{par}",
        "interval": TV_INTERVALOS.get(timeframe, "15"),
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "backgroundColor": "#0b0e11",
        "gridColor": "rgba(139,148,158,0.08)",
        "enable_publishing": False,
        "hide_side_toolbar": False,
        "allow_symbol_change": True,
        "studies": ["STD;RSI"],
        "container_id": "tradingview_chart",
    }
    return f"""
<div class="tradingview-widget-container" style="height:{altura}px;width:100%">
  <div id="tradingview_chart" style="height:100%;width:100%"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">new TradingView.widget({json.dumps(config)});</script>
</div>
"""

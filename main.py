import streamlit as st
import time
import pandas as pd
from services import MarketDataService, AIService
import io
import base64
import asyncio
import edge_tts 

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="TradeAI Pro", page_icon="📈", layout="wide")

# --- 2. CSS PERSONALIZADO ---
st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #ffffff; }
    .block-container { padding-top: 6rem; padding-bottom: 5rem; max-width: 1400px; }
    .btn-align { margin-top: 0px; }
    .btn-green button {
        background-color: #00c853 !important; color: white !important;
        border: 1px solid #00e676 !important; font-weight: bold !important; height: 42px !important;
    }
    .btn-green button:hover { background-color: #00e676 !important; box-shadow: 0 0 15px rgba(0, 200, 83, 0.5) !important; }
    .metric-card { background-color: #15191e; border: 1px solid #2b303b; border-radius: 12px; padding: 15px; }
    .metric-value { font-size: 22px; font-weight: bold; color: #ffffff; }
    .metric-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
    .metric-sub { font-size: 11px; font-weight: 500; }
    .green-text { color: #00c853; } .red-text { color: #ff5252; }
    .icon-box { float: right; width: 35px; height: 35px; background-color: #1e2329; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; }
    .ai-card { background-color: #1e2329; border: 1px solid #444; border-radius: 12px; padding: 20px; height: 280px; overflow-y: auto; display: flex; flex-direction: column; }
    .ai-title { color: #00c853; font-weight: bold; margin-bottom: 10px; font-size: 14px; border-bottom: 1px solid #333; padding-bottom: 8px; }
    .ai-text { font-size: 14px; color: #d1d5db; line-height: 1.6; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES (ÁUDIO SEGURO) ---
async def gerar_audio_bytes_memoria(texto, voz="pt-BR-FranciscaNeural"):
    communicate = edge_tts.Communicate(texto, voz)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    return mp3_fp.getvalue()

def rodar_async_seguro(coroutine):
    """Executa async sem quebrar o loop do Streamlit"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coroutine)

def autoplay_audio_bytes(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode()
    md = f"""
        <audio autoplay style="display:none;">
        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
    """
    st.markdown(md, unsafe_allow_html=True)

# --- 3. INICIALIZAÇÃO ---
market_service = MarketDataService()
ai_service = AIService()

if "analise_ativa" not in st.session_state: st.session_state.analise_ativa = False
if "ai_text_current" not in st.session_state: st.session_state.ai_text_current = "Aguardando início da IA..."
if "ai_text_last" not in st.session_state: st.session_state.ai_text_last = "Nenhuma análise anterior."

# --- 4. CABEÇALHO ---
c_logo, c_moeda, c_tempo, c_voz, c_btn = st.columns([2.5, 2, 1, 0.5, 1.2])

with c_logo:
    st.markdown("### 📈 TradeAI <span style='font-size:12px; color:#666; font-weight:normal'>| Pro</span>", unsafe_allow_html=True)

with c_moeda:
    lista_moedas = [
        "Polygon (POL)", "Bitcoin (BTC)", "Ethereum (ETH)", "Solana (SOL)", 
        "Litecoin (LTC)", "Dogecoin (DOGE)", "Polkadot (DOT)", "Chainlink (LINK)", 
        "Cosmos (ATOM)", "Aave (AAVE)", "Uniswap (UNI)", "Outro..."
    ]
    moeda_visivel = st.selectbox("Moeda", lista_moedas, label_visibility="collapsed")
    
    simbolo_map = {
        "Polygon (POL)": "POLUSDT", "Bitcoin (BTC)": "BTCUSDT", "Ethereum (ETH)": "ETHUSDT",
        "Solana (SOL)": "SOLUSDT", "Litecoin (LTC)": "LTCUSDT", "Dogecoin (DOGE)": "DOGEUSDT",
        "Polkadot (DOT)": "DOTUSDT", "Chainlink (LINK)": "LINKUSDT", 
        "Cosmos (ATOM)": "ATOMUSDT", "Aave (AAVE)": "AAVEUSDT", "Uniswap (UNI)": "UNIUSDT"
    }
    
    if moeda_visivel == "Outro...":
        simbolo_tecnico = st.text_input("Símbolo", "PEPEUSDT", label_visibility="collapsed").upper()
    else:
        simbolo_tecnico = simbolo_map.get(moeda_visivel, "POLUSDT")

with c_tempo:
    tempos_display = ["15 min", "5 min", "30 min", "1 h", "4 h"]
    tempo_selecionado = st.selectbox("Timer", tempos_display, label_visibility="collapsed")
    mapa_tempo = {"5 min": "5m", "15 min": "15m", "30 min": "30m", "1 h": "1h", "4 h": "4h"}
    timeframe_tecnico = mapa_tempo[tempo_selecionado]

with c_voz:
    st.markdown('<div class="btn-align">', unsafe_allow_html=True)
    voz_tipo = st.toggle("🔊", value=True, help="Voz Ativa")
    st.markdown('</div>', unsafe_allow_html=True)

with c_btn:
    st.markdown('<div class="btn-align btn-green">', unsafe_allow_html=True)
    if st.button("▶ INICIAR", use_container_width=True):
        st.session_state.analise_ativa = True
        # st.toast removido temporariamente para evitar conflito visual
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# --- 5. DADOS ---
dados = market_service.obter_dados_tecnicos(simbolo_tecnico, timeframe_tecnico)

if not dados:
    st.error("Erro fatal: Dados não retornados pelo serviço.")
    st.stop()

sentimento = "Neutro"
if dados['probabilidade'] > 60: sentimento = "Otimista 🚀"
elif dados['probabilidade'] < 40: sentimento = "Pessimista 🐻"

# --- 6. CARDS ---
col1, col2, col3, col4 = st.columns(4)

def card_html(titulo, valor, sub, icone, cor_sub=""):
    return f"""
    <div class="metric-card">
        <div class="icon-box">{icone}</div>
        <div class="metric-label">{titulo}</div>
        <div class="metric-value">${valor}</div>
        <div class="metric-sub {cor_sub}">{sub}</div>
    </div>
    """

with col1:
    st.markdown(card_html(f"Preço ({simbolo_tecnico[:3]})", f"{dados['preco']:,.4f}", f"RSI: {dados['rsi']:.1f}", "💲"), unsafe_allow_html=True)

with col2:
    if dados['ema21'] > 0:
        var_simulada = (dados['preco'] - dados['ema21']) / dados['ema21'] * 100
    else: var_simulada = 0.0
    cor_var = "green-text" if var_simulada > 0 else "red-text"
    icone_var = "📈" if var_simulada > 0 else "📉"
    st.markdown(card_html(f"Tendência ({tempo_selecionado})", f"{dados['preco']:,.4f}", f"{var_simulada:+.2f}% vs EMA21", icone_var, cor_var), unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-box">⚡</div>
        <div class="metric-label">Sentimento IA</div>
        <div class="metric-value" style="font-size: 20px;">{sentimento}</div>
        <div class="metric-sub">Probabilidade: {dados['probabilidade']}%</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    indice = int(dados['probabilidade'])
    lbl_indice = "Medo" if indice < 35 else "Ganância" if indice > 65 else "Neutro"
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-box">🌐</div>
        <div class="metric-label">Medo & Ganância</div>
        <div class="metric-value">{indice}/100</div>
        <div class="metric-sub">{lbl_indice}</div>
    </div>
    """, unsafe_allow_html=True)

with st.expander("ℹ️ Metodologia e Fontes dos Dados"):
    st.caption("Dados via Binance/Gate.io. Indicadores calculados via Pandas (RSI 14, EMA 21). IA via Google Gemini 1.5/2.0.")

st.write("") 

# --- 7. ESTRUTURA VISUAL DA IA (CRIADA ANTES DE PROCESSAR) ---
col_ia_atual, col_ia_history = st.columns(2)
audio_bytes_final = None

# Processamento Lógico
if st.session_state.analise_ativa:
    with st.spinner(f"🤖 Lendo mercado ({tempo_selecionado})..."):
        try:
            # 1. Atualiza Histórico
            if st.session_state.ai_text_current != "Aguardando início da IA...":
                st.session_state.ai_text_last = st.session_state.ai_text_current
            
            # 2. Chama IA
            dados['timeframe'] = tempo_selecionado
            analise_texto, modelo = ai_service.consultar_gemini(simbolo_tecnico, dados)
            st.session_state.ai_text_current = analise_texto
            
            # 3. Gera Áudio (Protegido)
            if voz_tipo:
                try:
                    # Remove asteriscos para o áudio ficar limpo
                    texto_limpo = analise_texto.replace("*", "")
                    audio_bytes_final = rodar_async_seguro(gerar_audio_bytes_memoria(texto_limpo))
                except Exception as e:
                    print(f"Erro Áudio: {e}") # Não trava o app, só loga
                    
        except Exception as e:
            st.error(f"Erro na Análise: {e}")
            
    st.session_state.analise_ativa = False

# Renderização Visual da IA
with col_ia_atual:
    st.markdown(f"""
    <div class="ai-card">
        <div class="ai-title">🧠 ANÁLISE IA ({tempo_selecionado}) <span>AGORA</span></div>
        <div class="ai-text">{st.session_state.ai_text_current}</div>
    </div>
    """, unsafe_allow_html=True)
    if audio_bytes_final:
        autoplay_audio_bytes(audio_bytes_final)

with col_ia_history:
    st.markdown(f"""
    <div class="ai-card">
        <div class="ai-title">📜 ÚLTIMO INSIGHT <span>HISTÓRICO</span></div>
        <div class="ai-text">{st.session_state.ai_text_last}</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# --- 8. GRÁFICO TRADINGVIEW ---
st.markdown("### 📊 Gráfico TradingView") 
import streamlit.components.v1 as components

tv_interval_map = {"5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240"}
tv_interval = tv_interval_map.get(timeframe_tecnico, "15")

# Fallback simples se o símbolo for complexo demais
symbol_tv = f"BINANCE:{simbolo_tecnico.replace('/','')}"

html_tv = f"""
<div class="tradingview-widget-container" style="height:500px;width:100%">
  <div id="tradingview_chart" style="height:calc(100% - 32px);width:100%"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "autosize": true,
    "symbol": "{symbol_tv}", 
    "interval": "{tv_interval}",
    "timezone": "America/Sao_Paulo",
    "theme": "dark",
    "style": "1",
    "locale": "br",
    "toolbar_bg": "#f1f3f6",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(html_tv, height=500)



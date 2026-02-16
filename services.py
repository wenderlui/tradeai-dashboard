import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv # Adicionei find_dotenv
import streamlit as st

# Carrega as variáveis de ambiente forçando a busca do arquivo
load_dotenv(find_dotenv()) 

# --- DIAGNÓSTICO (Aparecerá no terminal preto) ---
chave_teste = os.getenv("GEMINI_API_KEY")
if chave_teste:
    print(f"✅ SUCESSO: Chave encontrada! (Começa com: {chave_teste[:5]}...)")
else:
    print("❌ ERRO CRÍTICO: O arquivo .env não foi lido ou a chave não está lá.")
# -------------------------------------------------

class MarketDataService:
# ... (o resto do código continua igual)
    """
    Responsável por buscar dados brutos (Kraken) e calcular indicadores matemáticos.
    """
    def __init__(self):
        self.exchange = ccxt.kraken()

    def _resolver_simbolo(self, symbol_bybit):
        """Traduz o símbolo da UI (Bybit) para o Data Provider (Kraken)"""
        mapa = {
            "BTCUSDT": "BTC/USD", "ETHUSDT": "ETH/USD", "SOLUSDT": "SOL/USD",
            "XRPUSDT": "XRP/USD", "BNBUSDT": "BNB/USD", "DOGEUSDT": "DOGE/USD",
            "ADAUSDT": "ADA/USD", "AVAXUSDT": "AVAX/USD", "DOTUSDT": "DOT/USD",
            "LINKUSDT": "LINK/USD", "TRXUSDT": "TRX/USD", "POLUSDT": "POL/USD",
            "LTCUSDT": "LTC/USD", "BCHUSDT": "BCH/USD"
        }
        if symbol_bybit in mapa: return mapa[symbol_bybit]
        # Lógica genérica para moedas manuais
        base = symbol_bybit.upper().replace("USDT", "").replace("USD", "")
        return f"{base}/USD"

    def _calcular_probabilidade(self, df):
        """Algoritmo proprietário de decisão (0 a 100%)"""
        if len(df) < 50: return 50
        score = 50
        last = df.iloc[-1]
        
        # Regra 1: RSI (Oscilador)
        if last['rsi'] < 30: score += 20
        elif last['rsi'] > 70: score -= 20
        elif last['rsi'] > 55: score -= 5
        elif last['rsi'] < 45: score += 5

        # Regra 2: Cruzamento de Médias (Tendência Curta)
        if last['ema9'] > last['ema21']: score += 20
        else: score -= 20
        
        # Regra 3: Tendência Longa
        if last['close'] > last['ema50']: score += 10
        else: score -= 10
        
        return max(0, min(100, score))

    def obter_dados_tecnicos(self, symbol_bybit):
        """Método principal chamado pelo Front-end"""
        try:
            symbol_kraken = self._resolver_simbolo(symbol_bybit)
            candles = self.exchange.fetch_ohlcv(symbol_kraken, timeframe="15m", limit=100)
            
            if not candles or len(candles) < 50: return None
            
            df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            # Cálculos Vetorizados (Pandas)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            df['ema9'] = df['close'].ewm(span=9).mean()
            df['ema21'] = df['close'].ewm(span=21).mean()
            df['ema50'] = df['close'].ewm(span=50).mean()
            
            # Encapsula o resultado num objeto limpo (DTO)
            ultimo = df.iloc[-1]
            return {
                "preco": ultimo['close'],
                "rsi": ultimo['rsi'],
                "ema9": ultimo['ema9'],
                "ema21": ultimo['ema21'],
                "probabilidade": self._calcular_probabilidade(df)
            }
        except Exception as e:
            print(f"Erro Service: {e}")
            return None

class AIService:
    """
    Responsável pela inteligência artificial e conexões com LLMs.
    """
    def consultar_gemini(self, simbolo, dados_tecnicos):
         # Lista atualizada com seus modelos reais (Prioridade: Velocidade > Inteligência > Backup)
        modelos = [
            "gemini-2.0-flash",       # O novo padrão (Rápido e Inteligente)
            "gemini-2.0-flash-lite",  # Ultra rápido (Ótimo para não travar)
            "gemini-2.5-flash",       # Geração mais nova
            "gemini-2.5-pro"          # Mais inteligente (Backup de luxo)
        ]
        
        # Tenta pegar chave dos Secrets (Cloud) ou Env (Local)
        api_key = None
        try:
            if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
            else: api_key = os.getenv("GEMINI_API_KEY")
        except: pass

        if not api_key:
            return "⚠️ ERRO: Configure a GEMINI_API_KEY nos Secrets.", "Config Error"

        client = genai.Client(api_key=api_key)
        
        prompt = (
            f"Atue como Trader Institucional. Par: {simbolo}.\n"
            f"DADOS: Preço ${dados_tecnicos['preco']} | RSI: {dados_tecnicos['rsi']:.1f} | "
            f"Probabilidade Alta: {dados_tecnicos['probabilidade']}%\n"
            f"Responda CURTO:\n"
            f"VEREDITO: [COMPRA/VENDA/NEUTRO]\n"
            f"ANÁLISE: [Motivo técnico em 1 frase]"
        )

        for modelo in modelos:
            try:
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text, modelo
            except:
                continue
                
        return "⚠️ Cota Excedida. Aguarde...", "Offline"
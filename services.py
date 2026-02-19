import ccxt
import pandas as pd
import os
import time
import streamlit as st
from google import genai
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS (MULTI-EXCHANGE ROBUSTO) ---
class MarketDataService:
    def __init__(self):
        # Lista de tentativas ordenada por estabilidade
        self.exchanges = [
            ccxt.gateio({'enableRateLimit': True}),  # Gate.io costuma ser amigável com Cloud
            ccxt.kucoin({'enableRateLimit': True}),
            ccxt.binance({'enableRateLimit': True}),
        ]

    def _resolver_simbolo_e_timeframe(self, exchange, simbolo_entrada, timeframe):
        s = str(simbolo_entrada).upper().strip().replace(" ", "")
        
        # Mapa de pares
        pair = f"{s}/USDT"
        if "/" not in s:
            if s.endswith("USDT"): pair = s.replace("USDT", "/USDT")
            else: pair = f"{s}/USDT"
            
        return pair, timeframe

    def obter_dados_tecnicos(self, simbolo_entrada, timeframe='15m'):
        # 1. Tenta buscar em várias exchanges
        for exchange in self.exchanges:
            try:
                symbol_fmt, tf_fmt = self._resolver_simbolo_e_timeframe(exchange, simbolo_entrada, timeframe)
                
                # Tenta POL e depois MATIC se falhar
                tickers = [symbol_fmt]
                if "POL/" in symbol_fmt: tickers.append(symbol_fmt.replace("POL/", "MATIC/"))

                ohlcv = None
                for ticker in tickers:
                    try:
                        ohlcv = exchange.fetch_ohlcv(ticker, timeframe=tf_fmt, limit=60)
                        if ohlcv: break
                    except: continue

                if not ohlcv: continue # Próxima exchange

                # 2. Processa os dados (Pandas)
                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                
                # Cálculos
                df['delta'] = df['close'].diff()
                df['gain'] = df['delta'].where(df['delta'] > 0, 0)
                df['loss'] = -df['delta'].where(df['delta'] < 0, 0)
                
                avg_gain = df['gain'].rolling(14).mean()
                avg_loss = df['loss'].rolling(14).mean()
                rs = avg_gain / avg_loss
                df['rsi'] = 100 - (100 / (1 + rs))
                df['rsi'] = df['rsi'].fillna(50)
                
                df['ema9'] = df['close'].ewm(span=9).mean()
                df['ema21'] = df['close'].ewm(span=21).mean()
                
                ultimo = df.iloc[-1]
                
                # Probabilidade Simples
                prob = 50
                if ultimo['rsi'] < 30: prob += 20
                if ultimo['close'] > ultimo['ema21']: prob += 20
                
                return {
                    "preco": float(ultimo['close']),
                    "rsi": float(ultimo['rsi']),
                    "ema9": float(ultimo['ema9']),
                    "ema21": float(ultimo['ema21']),
                    "probabilidade": min(max(int(prob), 0), 100),
                    "timeframe": timeframe
                }

            except Exception as e:
                print(f"Erro na exchange {exchange.id}: {e}")
                continue

        # 3. FALHA TOTAL (Retorna zerado para não quebrar o site)
        return {
            "preco": 0.0,
            "rsi": 50.0,
            "ema9": 0.0,
            "ema21": 0.0,
            "probabilidade": 50,
            "erro": "Não foi possível obter dados."
        }

# --- SERVIÇO DE IA (INTEGRADO) ---
class AIService:
    def __init__(self):
        self.modelos = [
            "gemini-2.0-flash",       # O novo padrão (Rápido e Inteligente)
            "gemini-2.0-flash-lite",  # Ultra rápido (Ótimo para não travar)
            "gemini-2.5-flash",       # Geração mais nova
            "gemini-2.5-pro"          # Mais inteligente (Backup de luxo)
        ]
        try:
            self.api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        except: self.api_key = None

    def consultar_gemini(self, simbolo, dados):
        if not self.api_key: return "⚠️ Configure a API Key.", "Erro"
        
        # Se os dados estiverem zerados, avisa
        if dados['preco'] == 0:
            return "⚠️ Não consegui ler o mercado. Verifique o par ou tente mais tarde.", "Sem Dados"

        tf = dados.get('timeframe', '15m')
        
        prompt = f"""
        Aja como Trader Profissional. Analise {simbolo} ({tf}).
        Preço: {dados['preco']}
        RSI: {dados['rsi']:.1f} (Sobrecompra > 70, Sobrevenda < 30)
        EMA 21: {dados['ema21']:.2f}
        
        Responda em Português. Seja direto.
        Dê o VEREDITO: [COMPRA / VENDA / NEUTRO] e explique o porquê com base nos indicadores.
        """

        for modelo in self.modelos:
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text, modelo
            except:
                time.sleep(1)
                continue
        
        return "⚠️ IA indisponível no momento.", "Erro IA"


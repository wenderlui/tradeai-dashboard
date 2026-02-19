import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv
import time
import streamlit as st # Adicionado para mostrar erros na tela

load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS (MULTI-EXCHANGE) ---
class MarketDataService:
    def __init__(self):
        # Lista de tentativas: Se a Binance falhar (IP Block), tenta Gate.io, depois Huobi
        self.exchanges = [
            ccxt.gateio({'enableRateLimit': True}), # Gate costuma liberar IPs de Cloud
            ccxt.kucoin({'enableRateLimit': True}),
            ccxt.binance({'enableRateLimit': True}), 
        ]

    def _resolver_simbolo_e_timeframe(self, exchange, simbolo_entrada, timeframe):
        # 1. Ajuste do Símbolo
        s = str(simbolo_entrada).upper().strip().replace(" ", "")
        
        # Mapa de correção POL/MATIC
        pair = f"{s}/USDT"
        if "/" not in s:
            if s.endswith("USDT"): pair = s.replace("USDT", "/USDT")
            else: pair = f"{s}/USDT"
            
        # 2. Ajuste do Timeframe (Algumas exchanges usam '15' em vez de '15m')
        tf = timeframe
        if exchange.id == 'kucoin' and tf.endswith('m'):
            # Kucoin aceita '15m', mas vamos garantir
            pass 
            
        return pair, tf

    def obter_dados_tecnicos(self, simbolo_entrada, timeframe='15m'):
        erro_final = ""
        
        # Tenta em cada exchange da lista até conseguir
        for exchange in self.exchanges:
            try:
                symbol_fmt, tf_fmt = self._resolver_simbolo_e_timeframe(exchange, simbolo_entrada, timeframe)
                
                # Tenta buscar POL. Se falhar, tenta MATIC (pois muitas ainda não mudaram o nome)
                tickers_tentativa = [symbol_fmt]
                if "POL/" in symbol_fmt:
                    tickers_tentativa.append(symbol_fmt.replace("POL/", "MATIC/"))
                
                ohlcv = None
                pair_usado = ""
                
                for ticker in tickers_tentativa:
                    try:
                        ohlcv = exchange.fetch_ohlcv(ticker, timeframe=tf_fmt, limit=50)
                        if ohlcv:
                            pair_usado = ticker
                            break
                    except:
                        continue

                if not ohlcv:
                    continue # Tenta a próxima exchange
                
                # Se chegou aqui, deu certo! Processa os dados.
                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                
                # Cálculos Técnicos
                df['delta'] = df['close'].diff()
                df['gain'] = df['delta'].where(df['delta'] > 0, 0)
                df['loss'] = -df['delta'].where(df['delta'] < 0, 0)
                
                avg_gain = df['gain'].rolling(window=14).mean()
                avg_loss = df['loss'].rolling(window=14).mean()
                rs = avg_gain / avg_loss
                df['rsi'] = 100 - (100 / (1 + rs))
                df['rsi'] = df['rsi'].fillna(50)
                
                df['ema9'] = df['close'].ewm(span=9).mean()
                df['ema21'] = df['close'].ewm(span=21).mean()
                
                ultimo = df.iloc[-1]
                
                # Lógica Simples de Probabilidade
                prob = 50
                if ultimo['rsi'] < 30: prob += 25
                elif ultimo['rsi'] > 70: prob -= 25
                if ultimo['close'] > ultimo['ema21']: prob += 15
                else: prob -= 15
                
                # Aviso visual de qual fonte funcionou
                # st.toast(f"Dados obtidos via {exchange.name} ({pair_usado})") 
                
                return {
                    "preco": float(ultimo['close']),
                    "rsi": float(ultimo['rsi']),
                    "ema9": float(ultimo['ema9']),
                    "ema21": float(ultimo['ema21']),
                    "probabilidade": min(max(int(prob), 0), 100),
                    "timeframe": timeframe
                }

            except Exception as e:
                erro_final = str(e)
                continue # Tenta a próxima exchange

        # Se saiu do loop e nada funcionou:
        st.error(f"❌ Erro ao buscar dados: {erro_final}. Tente outro par ou tempo.")
        return None

# --- SERVIÇO DE IA ---
class AIService:
    def __init__(self):
        self.modelos = [
            "gemini-1.5-flash", 
            "gemini-2.0-flash", 
            "gemini-1.5-pro"
        ]
        self.api_key = None
        try:
            if "GEMINI_API_KEY" in st.secrets: 
                self.api_key = st.secrets["GEMINI_API_KEY"]
            else: 
                self.api_key = os.getenv("GEMINI_API_KEY")
        except: 
            self.api_key = os.getenv("GEMINI_API_KEY")

    def consultar_gemini(self, simbolo, dados):
        if not self.api_key: return "⚠️ Configure a GEMINI_API_KEY.", "Erro Config"
        if not dados or dados.get('preco', 0) == 0: return "⚠️ Sem dados de mercado.", "Erro Dados"

        tf = dados.get('timeframe', '15m')
        
        prompt = f"""
        Aja como Trader Crypto Profissional. 
        Analise {simbolo} no tempo gráfico {tf}.
        
        DADOS TÉCNICOS:
        - Preço: ${dados['preco']}
        - RSI (14): {dados['rsi']:.1f}
        - Média EMA 21: {dados['ema21']:.2f}
        - Tendência: {"ALTA" if dados['preco'] > dados['ema21'] else "BAIXA"}
        
        Responda em PT-BR (Máx 3 linhas).
        Dê um VEREDITO CLARO: [COMPRA / VENDA / NEUTRO] e explique usando o RSI e a Média.
        """

        for i, modelo in enumerate(self.modelos):
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text, modelo
            except Exception as e:
                time.sleep(1 + i)
                continue 
        
        return "⚠️ Erro na IA (Cota ou Conexão).", "Falha"

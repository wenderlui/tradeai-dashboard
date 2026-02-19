import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv
import time

load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS (BINANCE OFICIAL) ---
class MarketDataService:
    def __init__(self):
        # Binance é a melhor para POL atualmente
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
        })

    def _resolver_simbolo(self, simbolo_entrada):
        s = str(simbolo_entrada).upper().strip().replace(" ", "")
        
        # Correção Forçada para POL/MATIC
        if s in ["POL", "POLUSDT", "POL/USDT"]:
            return "POL/USDT"
        
        # Mapa padrão
        if s == "BTC": return "BTC/USDT"
        if s == "ETH": return "ETH/USDT"
        
        # Formatação Genérica
        if "/" not in s:
            if s.endswith("USDT"):
                return s.replace("USDT", "/USDT")
            else:
                return f"{s}/USDT"
        return s

    # Agora aceita o parametro 'timeframe'
    def obter_dados_tecnicos(self, simbolo_entrada, timeframe='15m'):
        symbol_fmt = self._resolver_simbolo(simbolo_entrada)
        print(f"🔍 Buscando {symbol_fmt} no tempo {timeframe}...")

        try:
            # Pega candles com o tempo certo (15m, 1h, 4h...)
            ohlcv = self.exchange.fetch_ohlcv(symbol_fmt, timeframe=timeframe, limit=100)
            
            if not ohlcv or len(ohlcv) < 20:
                print(f"❌ Sem dados para {symbol_fmt}")
                return None
                
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            # --- CÁLCULOS ---
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
            
            # Probabilidade
            prob = 50
            if ultimo['rsi'] < 30: prob += 20
            elif ultimo['rsi'] > 70: prob -= 20
            if ultimo['close'] > ultimo['ema21']: prob += 15
            
            return {
                "preco": float(ultimo['close']),
                "rsi": float(ultimo['rsi']),
                "ema9": float(ultimo['ema9']),
                "ema21": float(ultimo['ema21']),
                "probabilidade": min(max(int(prob), 0), 100)
            }
        except Exception as e:
            print(f"❌ Erro API: {e}")
            return None

# --- SERVIÇO DE IA (Mantido com melhorias de prompt) ---
class AIService:
    def __init__(self):
        self.modelos = [
            "gemini-1.5-flash", 
            "gemini-2.0-flash", 
            "gemini-1.5-pro"
        ]
        
        self.api_key = None
        try:
            if "GEMINI_API_KEY" in os.environ: 
                self.api_key = os.environ["GEMINI_API_KEY"]
            else:
                self.api_key = os.getenv("GEMINI_API_KEY")
        except: pass

    def consultar_gemini(self, simbolo, dados):
        if not self.api_key: return "⚠️ Configure a GEMINI_API_KEY.", "Erro"
        if not dados: return "⚠️ Aguardando dados...", "Erro"

        # Pega o timeframe que veio do main.py ou usa 15m padrão
        tf = dados.get('timeframe', '15 min')

        prompt = f"""
        Aja como Trader Profissional. Analise o par {simbolo} no gráfico de {tf}.
        Preço Atual: ${dados['preco']}
        RSI (14): {dados['rsi']:.1f}
        Média EMA 21: {dados['ema21']:.2f}
        Probabilidade Alta Calculada: {dados['probabilidade']}%
        
        Responda em PT-BR (máx 3 linhas).
        Dê o VEREDITO [COMPRA / VENDA / NEUTRO] para esse tempo gráfico ({tf}).
        Cite o RSI e a EMA na justificativa.
        """

        for i, modelo in enumerate(self.modelos):
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text, modelo
            except Exception as e:
                time.sleep(1 + i) # Espera progressiva
                continue
        
        return "⚠️ Cota excedida. Tente em 1 min.", "Falha"

import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv

# Carrega as senhas
load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS (AGORA COM BINANCE) ---
class MarketDataService:
    def __init__(self):
        # MUDANÇA: Usando Binance (Mais estável para dados públicos)
        self.exchange = ccxt.binance() 

    def _resolver_simbolo(self, simbolo_entrada):
        """
        Transforma o texto do usuário no formato da Binance
        """
        # Limpa espaços e joga para maiúsculo
        s = str(simbolo_entrada).upper().strip().replace(" ", "")
        
        # Mapa de apelidos comuns
        mapa = {
            "POL": "POL/USDT",
            "MATIC": "POL/USDT", # Binance já converteu MATIC para POL
            "BTC": "BTC/USDT",
            "ETH": "ETH/USDT",
            "DOGE": "DOGE/USDT",
            "PEPE": "PEPE/USDT",
            "SOL": "SOL/USDT"
        }
        
        if s in mapa:
            return mapa[s]

        # Lógica inteligente de formatação
        # Se tem barra, retorna (Ex: BTC/USDT)
        if "/" in s:
            return s
            
        # Se termina com USDT mas não tem barra (Ex: BTCUSDT -> BTC/USDT)
        if s.endswith("USDT"):
            return s.replace("USDT", "/USDT")
            
        # Se não tem nada, adiciona USDT (Ex: ADA -> ADA/USDT)
        return f"{s}/USDT"

    def obter_dados_tecnicos(self, simbolo):
        symbol_fmt = self._resolver_simbolo(simbolo)
        print(f"🔍 Buscando na Binance: {symbol_fmt}...") # Debug no terminal
        
        try:
            # Busca os últimos 100 candles de 15 minutos
            ohlcv = self.exchange.fetch_ohlcv(symbol_fmt, timeframe='15m', limit=100)
            
            if not ohlcv or len(ohlcv) < 20:
                print(f"❌ Binance não retornou dados suficientes para {symbol_fmt}")
                return None
                
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            # --- CÁLCULOS ---
            df['delta'] = df['close'].diff()
            df['gain'] = df['delta'].where(df['delta'] > 0, 0)
            df['loss'] = -df['delta'].where(df['delta'] < 0, 0)
            
            # RSI (Protegido contra divisão por zero)
            avg_gain = df['gain'].rolling(window=14).mean()
            avg_loss = df['loss'].rolling(window=14).mean()
            rs = avg_gain / avg_loss
            df['rsi'] = 100 - (100 / (1 + rs))
            df['rsi'] = df['rsi'].fillna(50) # Se der erro, assume neutro
            
            # Médias Móveis
            df['ema9'] = df['close'].ewm(span=9).mean()
            df['ema21'] = df['close'].ewm(span=21).mean()
            
            ultimo = df.iloc[-1]
            
            # Cálculo de Probabilidade (Simplificado)
            prob = 50
            if ultimo['rsi'] < 30: prob += 20
            elif ultimo['rsi'] > 70: prob -= 20
            if ultimo['close'] > ultimo['ema21']: prob += 15
            if ultimo['ema9'] > ultimo['ema21']: prob += 10
            
            print(f"✅ Dados recebidos! Preço: {ultimo['close']}")
            
            return {
                "preco": float(ultimo['close']),
                "rsi": float(ultimo['rsi']),
                "ema9": float(ultimo['ema9']),
                "ema21": float(ultimo['ema21']),
                "probabilidade": min(max(int(prob), 0), 100)
            }
            
        except Exception as e:
            print(f"❌ Erro crítico na API: {e}")
            return None

# --- SERVIÇO DE IA (SEM MUDANÇAS) ---
class AIService:
    def __init__(self):
        # Lista de modelos para rotação de falha
        self.modelos = [
            "gemini-2.0-flash",       # O novo padrão (Rápido e Inteligente)
            "gemini-2.0-flash-lite",  # Ultra rápido (Ótimo para não travar)
            "gemini-2.5-flash",       # Geração mais nova
            "gemini-2.5-pro"          # Mais inteligente (Backup de luxo)
        ]
        self.api_key = os.getenv("GEMINI_API_KEY")

    def consultar_gemini(self, simbolo, dados):
        # Validação extra antes de gastar cota da IA
        if not dados or dados.get('preco', 0) == 0:
            return "⚠️ DADOS INVÁLIDOS: O robô não conseguiu ler o mercado. Verifique o símbolo.", "Sistema"

        if not self.api_key:
            return "⚠️ Configure a GEMINI_API_KEY.", "Erro"

        prompt = f"""
        Aja como um Trader Profissional. Analise o par {simbolo}.
        Preço Atual: ${dados['preco']}
        RSI (14 períodos): {dados['rsi']:.1f}
        Média EMA 21: {dados['ema21']:.2f}
        
        Responda em Português do Brasil (PT-BR).
        Seja direto (máximo 3 linhas).
        Dê um veredito claro: COMPRA, VENDA ou NEUTRO e explique o motivo técnico.
        """

        for modelo in self.modelos:
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt
                )
                return response.text, modelo
            except Exception as e:
                print(f"⚠️ {modelo} falhou. Tentando próximo...")
                continue
        
        return "⚠️ IA indisponível. Tente novamente em 1 min.", "Erro"

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

# --- SERVIÇO DE IA (COM ROTAÇÃO AUTOMÁTICA CORRIGIDA) ---
class AIService:
    def __init__(self):
        # 1. DEFINIÇÃO DA LISTA DE MODELOS (Aqui é o lugar certo)
        self.modelos = [
            "gemini-2.0-flash",       # Prioridade 1: O mais novo
            "gemini-1.5-flash",       # Prioridade 2: O mais estável (Cavalo de batalha)
            "gemini-1.5-pro",         # Prioridade 3: Inteligência extra
        ]
        
        # Tenta pegar chave dos Secrets (Cloud) ou Env (Local)
        self.api_key = None
        try:
            if "GEMINI_API_KEY" in st.secrets: 
                self.api_key = st.secrets["GEMINI_API_KEY"]
            else: 
                self.api_key = os.getenv("GEMINI_API_KEY")
        except: 
            self.api_key = os.getenv("GEMINI_API_KEY")

    def consultar_gemini(self, simbolo, dados):
        # Verificação de segurança
        if not self.api_key:
            return "⚠️ Configure a GEMINI_API_KEY.", "Erro Config"

        if not dados or dados.get('preco', 0) == 0:
             return "⚠️ Aguardando dados do mercado...", "Sem Dados"

        # O Prompt para o Trader IA
        prompt = f"""
        Aja como Trader Profissional. Analise o par {simbolo}.
        Preço Atual: ${dados['preco']}
        RSI (14): {dados['rsi']:.1f}
        Média EMA 21: {dados['ema21']:.2f}
        Probabilidade Calc: {dados['probabilidade']}%
        
        Responda em Português (PT-BR). SEJA BREVE (Máx 3 linhas).
        Dê o VEREDITO: [COMPRA / VENDA / NEUTRO] e o motivo técnico.
        """
        # --- TRECHO PARA SUBSTITUIR O LOOP FOR ---
        
        # Loop de Tentativa e Erro (Rotação de Modelos)
       # --- LOOP DE ROTAÇÃO DE MODELOS (A MÁGICA ACONTECE AQUI) ---
        for modelo_atual in self.modelos:
            try:
                # Cria o cliente usando a chave
                client = genai.Client(api_key=self.api_key)
                
                # Tenta gerar a resposta com o modelo da vez
                response = client.models.generate_content(
                    model=modelo_atual,
                    contents=prompt
                )
                
                # Se der certo, RETORNA e sai da função.
                return response.text, modelo_atual

            except Exception as e:
                # Se der erro (Cota ou Modelo inexistente), apenas imprime e TENTA O PRÓXIMO
                print(f"⚠️ {modelo_atual} falhou: {e}. Tentando o próximo...")
                continue 
        
        # Se o loop terminar e nada funcionar:
        return "⚠️ Todos os modelos falharam (Cota Excedida).", "Falha Geral"



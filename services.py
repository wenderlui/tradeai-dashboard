import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv
import streamlit as st

# Carrega variáveis de ambiente
load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS DE MERCADO (Mantido igual) ---
class MarketDataService:
    def __init__(self):
        self.exchange = ccxt.bybit() # Usando Bybit que é estável

    def _resolver_simbolo(self, simbolo_entrada):
        """Traduz símbolos para o formato da exchange"""
        mapa = {
            "BTCUSDT": "BTC/USDT",
            "ETHUSDT": "ETH/USDT",
            "SOLUSDT": "SOL/USDT",
            "LTCUSDT": "LTC/USDT",
            "DOGEUSDT": "DOGE/USDT",
            "DOTUSDT": "DOT/USDT",
            "LINKUSDT": "LINK/USDT",
            "POLUSDT": "POL/USDT", # Bybit usa POL
            "ATOMUSDT": "ATOM/USDT",
            "AAVEUSDT": "AAVE/USDT",
            "UNIUSDT": "UNI/USDT"
        }
        return mapa.get(simbolo_entrada, simbolo_entrada)

    def obter_dados_tecnicos(self, simbolo):
        try:
            symbol_fmt = self._resolver_simbolo(simbolo)
            ohlcv = self.exchange.fetch_ohlcv(symbol_fmt, timeframe='15m', limit=100)
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            # Cálculos (RSI, EMA)
            df['delta'] = df['close'].diff()
            df['gain'] = df['delta'].where(df['delta'] > 0, 0)
            df['loss'] = -df['delta'].where(df['delta'] < 0, 0)
            avg_gain = df['gain'].rolling(window=14).mean()
            avg_loss = df['loss'].rolling(window=14).mean()
            rs = avg_gain / avg_loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            df['ema9'] = df['close'].ewm(span=9).mean()
            df['ema21'] = df['close'].ewm(span=21).mean()
            
            ultimo = df.iloc[-1]
            
            # Lógica simples de probabilidade
            prob = 50
            if ultimo['rsi'] < 30: prob += 20  # Sobrevenda (Chance de subir)
            elif ultimo['rsi'] > 70: prob -= 20 # Sobrecompra (Chance de cair)
            if ultimo['close'] > ultimo['ema21']: prob += 10
            
            return {
                "preco": ultimo['close'],
                "rsi": ultimo['rsi'],
                "ema9": ultimo['ema9'],
                "ema21": ultimo['ema21'],
                "probabilidade": min(max(prob, 0), 100)
            }
        except Exception as e:
            print(f"Erro ao obter dados: {e}")
            return None

# --- SERVIÇO DE IA (COM ROTAÇÃO AUTOMÁTICA) ---
class AIService:
    def __init__(self):
        # Lista de modelos por ordem de preferência (Velocidade -> Custo -> Inteligência)
        self.modelos = [
            "gemini-2.0-flash",       # O novo padrão (Rápido e Inteligente)
            "gemini-2.0-flash-lite",  # Ultra rápido (Ótimo para não travar)
            "gemini-2.5-flash",       # Geração mais nova
            "gemini-2.5-pro"          # Mais inteligente (Backup de luxo)
        ]
        
        self.api_key = os.getenv("GEMINI_API_KEY")

    def consultar_gemini(self, simbolo, dados):
        if not self.api_key:
            return "⚠️ Configure a GEMINI_API_KEY.", "Erro"

        prompt = f"""
        Aja como um Trader Profissional de Criptomoedas. Analise: {simbolo}.
        Preço: {dados['preco']}
        RSI (14): {dados['rsi']:.1f}
        Média EMA 21: {dados['ema21']}
        Probabilidade de Alta: {dados['probabilidade']}%
        
        Responda em PT-BR, curto e direto (máximo 3 linhas).
        Diga se é COMPRA, VENDA ou AGUARDAR e explique o motivo técnico.
        """

        # --- O SEGREDO: LOOP DE TENTATIVAS ---
        for modelo_atual in self.modelos:
            try:
                # Tenta conectar com o modelo da vez
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(
                    model=modelo_atual,
                    contents=prompt
                )
                
                # Se der certo, retorna imediatamente e interrompe o loop
                return response.text, modelo_atual

            except Exception as e:
                # Se der erro (Cota excedida, servidor ocupado, etc.)
                print(f"⚠️ Falha no modelo {modelo_atual}: {e}")
                # O loop continua automaticamente para o próximo modelo da lista
                continue
        
        # Se chegar aqui, é porque TODOS os modelos da lista falharam
        return "⚠️ Sistema sobrecarregado. Aguarde 30s.", "Falha Geral"

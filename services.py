import ccxt
import pandas as pd
import os
from google import genai
from dotenv import load_dotenv, find_dotenv
import streamlit as st

# Carrega variáveis
load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS DE MERCADO (CORRIGIDO) ---
class MarketDataService:
    def __init__(self):
        # Trocamos para Binance temporariamente se Bybit falhar, ou mantemos Bybit
        # Vamos usar Bybit pois não exige API Key para dados públicos
        self.exchange = ccxt.bybit() 

    def _resolver_simbolo(self, simbolo_entrada):
        """
        Transforma qualquer bagunça que o usuário digitar em um par válido.
        Ex: "pepe" -> "PEPE/USDT"
        Ex: "BTCUSDT" -> "BTC/USDT"
        """
        # 1. Remove espaços e joga pra maiúsculo
        s = simbolo_entrada.upper().strip()
        
        # 2. Mapa Manual (Para garantir os principais)
        mapa = {
            "BTCUSDT": "BTC/USDT",
            "ETHUSDT": "ETH/USDT",
            "SOLUSDT": "SOL/USDT",
            "LTCUSDT": "LTC/USDT",
            "POLUSDT": "POL/USDT", # Polygon
            "MATICUSDT": "MATIC/USDT", # Caso antigo
        }
        
        if s in mapa:
            return mapa[s]
            
        # 3. Tratamento Genérico (Para "Outro...")
        # Se o usuário digitou "PEPEUSDT" ou "PEPE", queremos "PEPE/USDT"
        
        # Remove a barra se tiver
        s = s.replace("/", "")
        
        # Se terminar com USDT, remove para formatar certo depois
        if s.endswith("USDT"):
            moeda_base = s.replace("USDT", "")
        else:
            moeda_base = s
            
        return f"{moeda_base}/USDT"

    def obter_dados_tecnicos(self, simbolo):
        symbol_fmt = self._resolver_simbolo(simbolo)
        
        try:
            # Tenta buscar os dados
            ohlcv = self.exchange.fetch_ohlcv(symbol_fmt, timeframe='15m', limit=100)
            
            # Se a lista vier vazia
            if not ohlcv:
                print(f"❌ Bybit retornou vazio para: {symbol_fmt}")
                return None
                
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
            if ultimo['rsi'] < 30: prob += 20
            elif ultimo['rsi'] > 70: prob -= 20
            if ultimo['close'] > ultimo['ema21']: prob += 10
            
            # Print de Sucesso no Terminal (Para você ver que funcionou)
            print(f"✅ Dados recebidos para {symbol_fmt}: Preço ${ultimo['close']}")
            
            return {
                "preco": ultimo['close'],
                "rsi": ultimo['rsi'],
                "ema9": ultimo['ema9'],
                "ema21": ultimo['ema21'],
                "probabilidade": min(max(prob, 0), 100)
            }
        except Exception as e:
            print(f"❌ Erro crítico ao buscar {symbol_fmt}: {e}")
            return None

# --- SERVIÇO DE IA (Mantido com Rotação) ---
class AIService:
    def __init__(self):
        selfmodelos = [
            "gemini-2.0-flash",       # O novo padrão (Rápido e Inteligente)
            "gemini-2.0-flash-lite",  # Ultra rápido (Ótimo para não travar)
            "gemini-2.5-flash",       # Geração mais nova
            "gemini-2.5-pro"          # Mais inteligente (Backup de luxo)
        ]
        self.api_key = os.getenv("GEMINI_API_KEY")

    def consultar_gemini(self, simbolo, dados):
        # Validação de dados zerados ANTES de chamar a IA
        if dados['preco'] == 0:
            return "⚠️ ERRO DE DADOS: Não consegui ler o preço da moeda. Verifique o símbolo.", "Sistema"

        if not self.api_key:
            return "⚠️ Configure a GEMINI_API_KEY.", "Erro"

        prompt = f"""
        Aja como Trader Crypto Profissional. Analise {simbolo}:
        Preço: {dados['preco']}
        RSI(14): {dados['rsi']:.1f}
        Média EMA21: {dados['ema21']:.2f}
        
        Responda em PT-BR (máximo 3 linhas).
        Dê o Veredito (COMPRA/VENDA/NEUTRO) e o motivo técnico curto.
        """

        for modelo_atual in self.modelos:
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(
                    model=modelo_atual,
                    contents=prompt
                )
                return response.text, modelo_atual
            except Exception as e:
                print(f"⚠️ {modelo_atual} falhou. Tentando próximo...")
                continue
        
        return "⚠️ IA Sobrecarregada. Tente em 30s.", "Falha"


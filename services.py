import ccxt
import pandas as pd
import os
import time
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# --- SERVIÇO DE DADOS (MANTIDO IGUAL) ---
class MarketDataService:
    def __init__(self):
        self.exchanges = [
            ccxt.gateio({'enableRateLimit': True}),
            ccxt.kucoin({'enableRateLimit': True}),
            ccxt.binance({'enableRateLimit': True}),
        ]

    def _resolver_simbolo_e_timeframe(self, exchange, simbolo_entrada, timeframe):
        s = str(simbolo_entrada).upper().strip().replace(" ", "")
        pair = f"{s}/USDT"
        if "/" not in s:
            if s.endswith("USDT"): pair = s.replace("USDT", "/USDT")
            else: pair = f"{s}/USDT"
        return pair, timeframe

    def obter_dados_tecnicos(self, simbolo_entrada, timeframe='15m'):
        for exchange in self.exchanges:
            try:
                symbol_fmt, tf_fmt = self._resolver_simbolo_e_timeframe(exchange, simbolo_entrada, timeframe)
                tickers = [symbol_fmt]
                if "POL/" in symbol_fmt: tickers.append(symbol_fmt.replace("POL/", "MATIC/"))

                ohlcv = None
                for ticker in tickers:
                    try:
                        ohlcv = exchange.fetch_ohlcv(ticker, timeframe=tf_fmt, limit=60)
                        if ohlcv: break
                    except: continue
                if not ohlcv: continue

                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                
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
                prob = 50
                if ultimo['rsi'] < 30: prob += 25
                elif ultimo['rsi'] > 70: prob -= 25
                if ultimo['close'] > ultimo['ema21']: prob += 15
                
                return {
                    "preco": float(ultimo['close']),
                    "rsi": float(ultimo['rsi']),
                    "ema9": float(ultimo['ema9']),
                    "ema21": float(ultimo['ema21']),
                    "probabilidade": min(max(int(prob), 0), 100),
                    "timeframe": timeframe
                }
            except: continue
        return {"preco": 0.0, "rsi": 50.0, "ema9": 0.0, "ema21": 0.0, "probabilidade": 50}

# --- SERVIÇO DE IA (ROTAÇÃO COM FEEDBACK VISUAL) ---
class AIService:
    def __init__(self):
        # NOVA LISTA DE PRIORIDADE (Do mais leve para o mais pesado)
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
        if not self.api_key: 
            return self._analise_offline(dados, "Chave API não configurada.")
        
        if dados.get('preco', 0) == 0:
            return "⚠️ Aguardando dados...", "Sem Dados"

        tf = dados.get('timeframe', '15m')
        
        # Prompt otimizado para gastar menos tokens
        prompt = f"""
        Analise {simbolo} ({tf}).
        Preço: {dados['preco']} | RSI: {dados['rsi']:.1f} | EMA21: {dados['ema21']:.2f}
        Veredito [COMPRA/VENDA/NEUTRO] em PT-BR.
        """

        ultimo_erro = ""

        # LOOP DE TENTATIVAS COM TOAST
        for i, modelo in enumerate(self.modelos):
            try:
                # Aviso visual (Some em 2 segundos)
                # st.toast(f"🔄 Tentando IA {i+1}: {modelo}...", icon="🤖")
                
                client = genai.Client(api_key=self.api_key)
                
                # Configuração para gastar menos tokens (baratear o custo)
                response = client.models.generate_content(
                    model=modelo, 
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=150, # Resposta curta
                        temperature=0.5
                    )
                )
                
                # Se deu certo, retorna imediatamente
                return response.text, modelo

            except Exception as e:
                erro_curto = str(e)
                if "429" in erro_curto: erro_curto = "Cota Excedida (429)"
                
                # Mostra o erro na tela para você ver a troca acontecendo
                print(f"❌ {modelo} falhou: {erro_curto}")
                st.toast(f"❌ {modelo} falhou. Trocando...", icon="⚠️")
                
                ultimo_erro = erro_curto
                time.sleep(2) # Espera 2s para garantir
                continue # VAI PARA O PRÓXIMO MODELO DA LISTA
        
        # Se saiu do loop, todos falharam -> Modo Offline
        return self._analise_offline(dados, f"Todas IAs falharam. Último erro: {ultimo_erro}")

    def _analise_offline(self, dados, motivo):
        """Backup matemático"""
        rsi = dados['rsi']
        sinal = "NEUTRO"
        if rsi < 30: sinal = "COMPRA (RSI Baixo)"
        elif rsi > 70: sinal = "VENDA (RSI Alto)"
        elif dados['preco'] > dados['ema21']: sinal = "COMPRA (Tendência de Alta)"
        
        return f"⚠️ **Modo Offline:** {motivo}\n\n**Análise Matemática:** O mercado indica {sinal} baseado nos indicadores técnicos.", "Backup Local"

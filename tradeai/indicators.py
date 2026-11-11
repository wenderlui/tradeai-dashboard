"""Indicadores técnicos e regras de pontuação (funções puras, fáceis de testar)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def ema(series: pd.Series, span: int) -> pd.Series:
    """Média móvel exponencial padrão (mesma fórmula do TradingView)."""
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI com suavização de Wilder (padrão de mercado).

    Retorna 50 enquanto não há dados suficientes, 100 quando só houve altas
    e 0 quando só houve quedas no período.
    """
    delta = close.astype(float).diff().to_numpy()
    n = len(delta)
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    if n > period:
        gains = np.clip(delta, 0, None)
        losses = np.clip(-delta, 0, None)
        # Semente: média simples dos primeiros `period` movimentos; depois, suavização de Wilder.
        g = gains[1 : period + 1].mean()
        l_ = losses[1 : period + 1].mean()
        avg_gain[period], avg_loss[period] = g, l_
        for i in range(period + 1, n):
            g = (g * (period - 1) + gains[i]) / period
            l_ = (l_ * (period - 1) + losses[i]) / period
            avg_gain[i], avg_loss[i] = g, l_

    avg_gain = pd.Series(avg_gain, index=close.index)
    avg_loss = pd.Series(avg_loss, index=close.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # Sem perdas no período: RSI = 100. Sem ganhos e sem perdas: 50 (lateral).
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return out.fillna(50.0)


def ohlcv_to_frame(ohlcv: list[list[float]]) -> pd.DataFrame:
    """Converte a resposta do ccxt em DataFrame com os indicadores calculados."""
    df = pd.DataFrame(ohlcv, columns=OHLCV_COLUMNS)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    for col in OHLCV_COLUMNS[1:]:
        df[col] = df[col].astype(float)
    df["rsi"] = rsi(df["close"])
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    return df


@dataclass
class Score:
    valor: int
    rotulo: str
    motivos: list[str] = field(default_factory=list)


def score_tecnico(preco: float, rsi_atual: float, ema9: float, ema21: float) -> Score:
    """Pontuação de 0 a 100 combinando RSI e tendência das médias.

    50 = neutro, acima de 60 = viés de alta, abaixo de 40 = viés de baixa.
    """
    pontos = 50
    motivos: list[str] = []

    if rsi_atual < 30:
        pontos += 20
        motivos.append(f"RSI {rsi_atual:.1f} em sobrevenda")
    elif rsi_atual > 70:
        pontos -= 20
        motivos.append(f"RSI {rsi_atual:.1f} em sobrecompra")
    elif rsi_atual >= 50:
        pontos += 5
        motivos.append(f"RSI {rsi_atual:.1f} com momento comprador")
    else:
        pontos -= 5
        motivos.append(f"RSI {rsi_atual:.1f} com momento vendedor")

    if ema21 > 0:
        if preco > ema21:
            pontos += 15
            motivos.append("Preço acima da EMA21")
        elif preco < ema21:
            pontos -= 15
            motivos.append("Preço abaixo da EMA21")

        if ema9 > ema21:
            pontos += 10
            motivos.append("EMA9 acima da EMA21 (tendência de alta)")
        elif ema9 < ema21:
            pontos -= 10
            motivos.append("EMA9 abaixo da EMA21 (tendência de baixa)")

    valor = int(min(max(pontos, 0), 100))
    return Score(valor=valor, rotulo=rotulo_score(valor), motivos=motivos)


def rotulo_score(valor: int) -> str:
    if valor >= 75:
        return "Alta forte"
    if valor > 60:
        return "Alta"
    if valor <= 25:
        return "Baixa forte"
    if valor < 40:
        return "Baixa"
    return "Neutro"


def zona_rsi(valor: float) -> str:
    if valor < 30:
        return "Sobrevenda"
    if valor > 70:
        return "Sobrecompra"
    return "Zona neutra"


def variacao_percentual(atual: float, referencia: float) -> float:
    if not referencia:
        return 0.0
    return (atual - referencia) / referencia * 100


def normalizar_simbolo(entrada: str, quote: str = "USDT") -> str:
    """Converte 'btc', 'BTCUSDT', 'btc/usdt' ou 'BTC-USDT' em 'BTC/USDT'."""
    s = str(entrada or "").upper().strip().replace(" ", "").replace("-", "/").replace("_", "/")
    if not s:
        raise ValueError("Informe um símbolo, por exemplo BTC ou BTCUSDT.")
    if "/" in s:
        base, _, q = s.partition("/")
        if not base or not q:
            raise ValueError(f"Símbolo inválido: {entrada!r}")
        return f"{base}/{q}"
    if s.endswith(quote) and len(s) > len(quote):
        return f"{s[: -len(quote)]}/{quote}"
    return f"{s}/{quote}"


def ativo_base(simbolo: str) -> str:
    """'DOGE/USDT' -> 'DOGE'."""
    return normalizar_simbolo(simbolo).split("/")[0]


def formatar_preco(valor: float) -> str:
    """Casas decimais adaptadas ao tamanho do preço (BTC vs PEPE)."""
    if valor == 0:
        return "0.00"
    absoluto = abs(valor)
    if absoluto >= 1000:
        return f"{valor:,.2f}"
    if absoluto >= 1:
        return f"{valor:,.4f}"
    if absoluto >= 0.01:
        return f"{valor:,.5f}"
    return f"{valor:.8f}".rstrip("0")

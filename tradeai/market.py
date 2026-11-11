"""Coleta de dados de mercado com fallback entre corretoras."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .indicators import Score, normalizar_simbolo, ohlcv_to_frame, score_tecnico, variacao_percentual

log = logging.getLogger(__name__)

# Ordem de preferência. Os nomes mudam entre versões do ccxt
# ("gateio" virou "gate"), por isso cada item aceita aliases.
EXCHANGES_PADRAO: list[tuple[str, ...]] = [("binance",), ("gate", "gateio"), ("kucoin",), ("okx",), ("bybit",)]

# Tokens renomeados: se o novo não existir numa corretora, tenta o antigo.
ALIASES_ATIVOS = {"POL": ["MATIC"]}

TIMEFRAMES = {"5 min": "5m", "15 min": "15m", "30 min": "30m", "1 h": "1h", "4 h": "4h", "1 dia": "1d"}

CANDLES = 200


class DadosIndisponiveis(Exception):
    """Nenhuma corretora retornou dados para o par solicitado."""


@dataclass
class Snapshot:
    simbolo: str
    timeframe: str
    exchange: str
    df: pd.DataFrame
    preco: float
    rsi: float
    ema9: float
    ema21: float
    variacao: float
    maxima: float
    minima: float
    score: Score
    avisos: list[str] = field(default_factory=list)

    def para_prompt(self) -> dict[str, Any]:
        return {
            "simbolo": self.simbolo,
            "timeframe": self.timeframe,
            "exchange": self.exchange,
            "preco": self.preco,
            "rsi": self.rsi,
            "ema9": self.ema9,
            "ema21": self.ema21,
            "variacao": self.variacao,
            "maxima": self.maxima,
            "minima": self.minima,
            "score": self.score.valor,
            "tendencia": self.score.rotulo,
        }


def criar_exchanges(nomes: Iterable[tuple[str, ...]] = EXCHANGES_PADRAO) -> list[Any]:
    import ccxt

    instancias = []
    for aliases in nomes:
        for nome in aliases:
            classe = getattr(ccxt, nome, None)
            if classe is not None:
                instancias.append(classe({"enableRateLimit": True, "timeout": 10000}))
                break
        else:
            log.warning("Corretora %s não existe nesta versão do ccxt", aliases[0])
    return instancias


class MarketDataService:
    def __init__(self, exchanges: list[Any] | None = None, exchange_factory: Callable[[], list[Any]] = criar_exchanges):
        self._exchanges = exchanges
        self._factory = exchange_factory

    @property
    def exchanges(self) -> list[Any]:
        if self._exchanges is None:
            self._exchanges = self._factory()
        return self._exchanges

    @staticmethod
    def candidatos(simbolo: str) -> list[str]:
        par = normalizar_simbolo(simbolo)
        base, quote = par.split("/")
        return [par] + [f"{alias}/{quote}" for alias in ALIASES_ATIVOS.get(base, [])]

    def buscar_candles(
        self, simbolo: str, timeframe: str = "15m", limit: int = CANDLES
    ) -> tuple[pd.DataFrame, str, str]:
        """Retorna (df, nome_da_corretora, par_usado). Lança DadosIndisponiveis se tudo falhar."""
        erros: list[str] = []
        for exchange in self.exchanges:
            nome = getattr(exchange, "id", type(exchange).__name__)
            for par in self.candidatos(simbolo):
                try:
                    ohlcv = exchange.fetch_ohlcv(par, timeframe=timeframe, limit=limit)
                except Exception as exc:  # erros de rede, par inexistente, etc.
                    erros.append(f"{nome} {par}: {type(exc).__name__}")
                    log.info("Falha em %s %s: %s", nome, par, exc)
                    continue
                if ohlcv and len(ohlcv) >= 2:
                    return ohlcv_to_frame(ohlcv), nome, par
                erros.append(f"{nome} {par}: sem candles")
        detalhe = "; ".join(erros[-4:]) or "nenhuma corretora configurada"
        raise DadosIndisponiveis(f"Não foi possível obter dados de {simbolo}. ({detalhe})")

    def snapshot(self, simbolo: str, timeframe: str = "15m") -> Snapshot:
        df, exchange, par = self.buscar_candles(simbolo, timeframe)
        return montar_snapshot(df, par, timeframe, exchange)


def montar_snapshot(df: pd.DataFrame, simbolo: str, timeframe: str, exchange: str) -> Snapshot:
    ultimo = df.iloc[-1]
    janela = df.tail(min(len(df), 50))
    preco = float(ultimo["close"])
    avisos = []
    if len(df) < 30:
        avisos.append("Poucos candles disponíveis: indicadores podem ser imprecisos.")
    return Snapshot(
        simbolo=simbolo,
        timeframe=timeframe,
        exchange=exchange,
        df=df,
        preco=preco,
        rsi=float(ultimo["rsi"]),
        ema9=float(ultimo["ema9"]),
        ema21=float(ultimo["ema21"]),
        variacao=variacao_percentual(preco, float(df["close"].iloc[0])),
        maxima=float(janela["high"].max()),
        minima=float(janela["low"].min()),
        score=score_tecnico(preco, float(ultimo["rsi"]), float(ultimo["ema9"]), float(ultimo["ema21"])),
        avisos=avisos,
    )


_MINUTOS = {"m": 1, "h": 60, "d": 1440}


def dados_demo(simbolo: str = "BTC/USDT", timeframe: str = "15m", n: int = CANDLES, seed: int = 7) -> Snapshot:
    """Série sintética para o modo demonstração (sem internet / sem corretora)."""
    rng = np.random.default_rng(seed + sum(map(ord, simbolo)))
    base = {"BTC": 68000.0, "ETH": 3500.0, "SOL": 160.0, "DOGE": 0.16, "PEPE": 0.0000123}.get(
        simbolo.split("/")[0], 1.25
    )
    passo_min = int(timeframe[:-1]) * _MINUTOS.get(timeframe[-1], 1)
    retornos = rng.normal(0.0002, 0.006, n)
    fechamentos = base * np.exp(np.cumsum(retornos))
    aberturas = np.concatenate([[base], fechamentos[:-1]])
    amplitude = np.abs(rng.normal(0, 0.003, n)) * fechamentos
    agora = pd.Timestamp.now(tz="UTC").floor(f"{passo_min}min")
    tempos = pd.date_range(end=agora, periods=n, freq=f"{passo_min}min")
    ohlcv = [
        [
            int(t.value // 1_000_000),
            float(o),
            float(max(o, c) + a),
            float(min(o, c) - a),
            float(c),
            float(abs(rng.normal(1000, 300))),
        ]
        for t, o, c, a in zip(tempos, aberturas, fechamentos, amplitude, strict=True)
    ]
    df = ohlcv_to_frame(ohlcv)
    return montar_snapshot(df, normalizar_simbolo(simbolo), timeframe, "demo")

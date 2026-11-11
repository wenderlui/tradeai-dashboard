import math

import pandas as pd
import pytest

from tradeai.indicators import (
    ativo_base,
    ema,
    formatar_preco,
    normalizar_simbolo,
    ohlcv_to_frame,
    rotulo_score,
    rsi,
    score_tecnico,
    variacao_percentual,
    zona_rsi,
)


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("BTCUSDT", "BTC/USDT"),
        ("btc", "BTC/USDT"),
        (" pepe usdt ", "PEPE/USDT"),
        ("ETH/USDT", "ETH/USDT"),
        ("eth-btc", "ETH/BTC"),
        ("SOL_USDT", "SOL/USDT"),
        ("USDT", "USDT/USDT"),
    ],
)
def test_normalizar_simbolo(entrada, esperado):
    assert normalizar_simbolo(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "/USDT", "BTC/"])
def test_normalizar_simbolo_invalido(entrada):
    with pytest.raises(ValueError):
        normalizar_simbolo(entrada)


def test_ativo_base_nao_corta_tickers_longos():
    # Bug antigo: simbolo[:3] mostrava "DOG" e "LIN".
    assert ativo_base("DOGEUSDT") == "DOGE"
    assert ativo_base("LINK/USDT") == "LINK"


def test_ema_igual_formula_classica():
    serie = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    resultado = ema(serie, 3)
    alpha = 2 / (3 + 1)
    esperado = 1.0
    for v in serie[1:]:
        esperado = alpha * v + (1 - alpha) * esperado
    assert resultado.iloc[-1] == pytest.approx(esperado)


def test_rsi_extremos():
    assert rsi(pd.Series(range(1, 40), dtype=float)).iloc[-1] == pytest.approx(100)
    assert rsi(pd.Series(range(40, 1, -1), dtype=float)).iloc[-1] == pytest.approx(0)
    assert rsi(pd.Series([10.0] * 30)).iloc[-1] == pytest.approx(50)


def test_rsi_valor_de_referencia():
    # Exemplo clássico de Wilder (New Concepts in Technical Trading Systems).
    precos = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
        46.00,
        46.03,
        46.41,
        46.22,
        45.64,
    ]
    valores = rsi(pd.Series(precos))
    assert 0 <= valores.min() and valores.max() <= 100
    assert valores.iloc[14] == pytest.approx(70.46, abs=0.6)
    assert not valores.isna().any()


def test_rsi_aquecimento_retorna_50():
    assert (rsi(pd.Series([1.0, 2.0, 3.0])) == 50).all()


def test_ohlcv_to_frame(ohlcv_alta):
    df = ohlcv_to_frame(ohlcv_alta)
    assert list(df.columns[:6]) == ["time", "open", "high", "low", "close", "volume"]
    assert str(df["time"].dt.tz) == "UTC"
    assert {"rsi", "ema9", "ema21"} <= set(df.columns)
    assert df["ema9"].iloc[-1] > df["ema21"].iloc[-1]


def test_score_alta_e_baixa():
    alta = score_tecnico(preco=110, rsi_atual=60, ema9=105, ema21=100)
    baixa = score_tecnico(preco=90, rsi_atual=40, ema9=95, ema21=100)
    assert alta.valor > 60 and alta.rotulo.startswith("Alta")
    assert baixa.valor < 40 and baixa.rotulo.startswith("Baixa")
    assert alta.motivos and baixa.motivos


def test_score_e_simetrico_e_limitado():
    # Bug antigo: só somava pontos quando o preço estava acima da EMA21.
    alta = score_tecnico(110, 55, 105, 100).valor
    baixa = score_tecnico(90, 45, 95, 100).valor
    assert alta - 50 == 50 - baixa
    for r in (0, 15, 50, 85, 100):
        for p in (0.5, 1, 2):
            assert 0 <= score_tecnico(p * 100, r, 100, 100).valor <= 100


def test_score_sem_ema():
    assert score_tecnico(10, 50, 0, 0).valor == 55


@pytest.mark.parametrize(
    "valor, rotulo", [(80, "Alta forte"), (65, "Alta"), (50, "Neutro"), (35, "Baixa"), (10, "Baixa forte")]
)
def test_rotulo_score(valor, rotulo):
    assert rotulo_score(valor) == rotulo


def test_zona_rsi():
    assert zona_rsi(20) == "Sobrevenda"
    assert zona_rsi(80) == "Sobrecompra"
    assert zona_rsi(50) == "Zona neutra"


def test_variacao_percentual():
    assert variacao_percentual(110, 100) == pytest.approx(10)
    assert variacao_percentual(5, 0) == 0.0


@pytest.mark.parametrize(
    "valor, esperado",
    [(67028.7254, "67,028.73"), (3.14159, "3.1416"), (0.16234, "0.16234"), (0.0000123, "0.0000123"), (0, "0.00")],
)
def test_formatar_preco(valor, esperado):
    assert formatar_preco(valor) == esperado
    assert not math.isnan(float(formatar_preco(valor).replace(",", "")))

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def gerar_ohlcv(fechamentos, inicio=1_700_000_000_000, passo=60_000):
    linhas = []
    anterior = fechamentos[0]
    for i, c in enumerate(fechamentos):
        linhas.append([inicio + i * passo, anterior, max(anterior, c) + 1, min(anterior, c) - 1, c, 100.0])
        anterior = c
    return linhas


@pytest.fixture
def ohlcv_alta():
    return gerar_ohlcv([100 + i for i in range(60)])


@pytest.fixture
def ohlcv_baixa():
    return gerar_ohlcv([200 - i for i in range(60)])


@pytest.fixture(autouse=True)
def sem_chave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    monkeypatch.delenv("TRADEAI_DEMO", raising=False)

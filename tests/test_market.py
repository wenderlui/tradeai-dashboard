import pytest

from tradeai.market import DadosIndisponiveis, MarketDataService, criar_exchanges, dados_demo


class FakeExchange:
    def __init__(self, id, dados=None, erro=None, pares=None):
        self.id = id
        self.dados = dados
        self.erro = erro
        self.pares = pares  # se definido, só responde para esses pares
        self.chamadas = []

    def fetch_ohlcv(self, par, timeframe="15m", limit=200):
        self.chamadas.append((par, timeframe, limit))
        if self.erro:
            raise self.erro
        if self.pares is not None and par not in self.pares:
            raise ValueError(f"{par} não listado")
        return self.dados


def test_usa_primeira_corretora_que_responde(ohlcv_alta):
    falha = FakeExchange("binance", erro=ConnectionError("offline"))
    ok = FakeExchange("gate", dados=ohlcv_alta)
    nunca = FakeExchange("kucoin", dados=ohlcv_alta)
    snap = MarketDataService([falha, ok, nunca]).snapshot("BTCUSDT", "1h")

    assert snap.exchange == "gate"
    assert snap.simbolo == "BTC/USDT"
    assert snap.timeframe == "1h"
    assert ok.chamadas == [("BTC/USDT", "1h", 200)]
    assert nunca.chamadas == []


def test_pol_tenta_alias_matic(ohlcv_alta):
    ex = FakeExchange("kucoin", dados=ohlcv_alta, pares={"MATIC/USDT"})
    snap = MarketDataService([ex]).snapshot("POL")
    assert snap.simbolo == "MATIC/USDT"
    assert [c[0] for c in ex.chamadas] == ["POL/USDT", "MATIC/USDT"]


def test_todas_falham_gera_erro_claro():
    # Bug antigo: retornava preço 0 silenciosamente e a tela mostrava "$0.0000".
    svc = MarketDataService([FakeExchange("binance", erro=TimeoutError()), FakeExchange("gate", dados=[])])
    with pytest.raises(DadosIndisponiveis, match="BTC"):
        svc.snapshot("BTC")


def test_sem_corretoras():
    with pytest.raises(DadosIndisponiveis, match="nenhuma corretora"):
        MarketDataService([]).snapshot("BTC")


def test_snapshot_calcula_metricas(ohlcv_alta):
    snap = MarketDataService([FakeExchange("binance", dados=ohlcv_alta)]).snapshot("ETH/USDT")
    assert snap.preco == 159
    assert snap.variacao == pytest.approx((159 - 100) / 100 * 100)
    assert snap.rsi == pytest.approx(100)
    assert snap.maxima >= snap.preco >= snap.minima
    assert snap.score.valor < 50 or snap.score.valor > 50
    dados = snap.para_prompt()
    assert dados["simbolo"] == "ETH/USDT" and dados["exchange"] == "binance"


def test_aviso_com_poucos_candles(ohlcv_alta):
    snap = MarketDataService([FakeExchange("binance", dados=ohlcv_alta[:10])]).snapshot("BTC")
    assert snap.avisos


def test_factory_e_preguicosa(ohlcv_alta):
    criadas = []

    def factory():
        criadas.append(1)
        return [FakeExchange("binance", dados=ohlcv_alta)]

    svc = MarketDataService(exchange_factory=factory)
    assert criadas == []
    svc.snapshot("BTC")
    svc.snapshot("ETH")
    assert criadas == [1]


def test_criar_exchanges_compativel_com_ccxt_atual():
    # Bug antigo: ccxt.gateio não existe mais nas versões novas e o app quebrava ao abrir.
    ids = [e.id for e in criar_exchanges()]
    assert "binance" in ids
    assert any(i in ("gate", "gateio") for i in ids)


def test_criar_exchanges_ignora_inexistentes():
    assert [e.id for e in criar_exchanges([("nao_existe",), ("binance",)])] == ["binance"]


@pytest.mark.parametrize("tf", ["5m", "15m", "1h", "4h", "1d"])
def test_dados_demo(tf):
    snap = dados_demo("SOL/USDT", tf)
    assert snap.exchange == "demo"
    assert len(snap.df) == 200
    assert snap.preco > 0
    assert (snap.df["high"] >= snap.df["low"]).all()
    assert snap.df["time"].is_monotonic_increasing

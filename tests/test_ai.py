from types import SimpleNamespace

import pytest

from tradeai import ai
from tradeai.ai import AIService, analise_offline, modelos_configurados, montar_prompt

DADOS = {
    "simbolo": "BTC/USDT",
    "timeframe": "15m",
    "exchange": "binance",
    "preco": 100.0,
    "rsi": 55.0,
    "ema9": 99.0,
    "ema21": 98.0,
    "variacao": 1.5,
    "maxima": 105.0,
    "minima": 95.0,
    "score": 70,
    "tendencia": "Alta",
}


class FakeModels:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def generate_content(self, model, contents):
        self.chamadas.append(model)
        r = self.respostas.get(model)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(text=r)


def servico(respostas, modelos=("m1", "m2", "m3"), **kw):
    models = FakeModels(respostas)
    esperas = []
    svc = AIService(
        api_key="chave",
        modelos=list(modelos),
        client_factory=lambda k: SimpleNamespace(models=models),
        sleep=esperas.append,
        **kw,
    )
    return svc, models, esperas


def test_sem_chave_usa_offline():
    svc = AIService(api_key="", client_factory=lambda k: pytest.fail("não deveria criar cliente"))
    res = svc.analisar(DADOS)
    assert res.offline and "GEMINI_API_KEY" in res.motivo
    assert not svc.configurada


def test_sem_preco():
    svc, models, _ = servico({"m1": "ok"})
    res = svc.analisar({**DADOS, "preco": 0})
    assert res.offline and models.chamadas == []


def test_primeiro_modelo_ok():
    svc, models, esperas = servico({"m1": "  **Veredito:** COMPRA  "})
    res = svc.analisar(DADOS)
    assert res.texto == "**Veredito:** COMPRA" and res.modelo == "m1" and not res.offline
    assert models.chamadas == ["m1"] and esperas == []


def test_rotaciona_modelos_em_falha():
    svc, models, esperas = servico({"m1": RuntimeError("429 RESOURCE_EXHAUSTED"), "m2": "", "m3": "ok"})
    res = svc.analisar(DADOS)
    assert res.modelo == "m3"
    assert models.chamadas == ["m1", "m2", "m3"]
    assert len(esperas) == 2


def test_todos_falham_sem_espera_no_final():
    svc, models, esperas = servico({m: RuntimeError("429 quota") for m in ("m1", "m2", "m3")})
    res = svc.analisar(DADOS)
    assert res.offline and "cota excedida" in res.motivo
    assert len(esperas) == 2  # bug antigo: esperava 2 s também após a última falha


def test_chave_invalida_para_imediatamente():
    svc, models, _ = servico({"m1": RuntimeError("400 API key not valid. API_KEY_INVALID")})
    res = svc.analisar(DADOS)
    assert models.chamadas == ["m1"]
    assert res.offline and "chave" in res.motivo


def test_falha_ao_criar_cliente():
    def quebra(_):
        raise RuntimeError("sem rede")

    res = AIService(api_key="x", modelos=["m"], client_factory=quebra).analisar(DADOS)
    assert res.offline and "sem rede" in res.motivo


def test_cliente_reutilizado():
    criados = []
    models = FakeModels({"m": "ok"})

    def factory(k):
        criados.append(k)
        return SimpleNamespace(models=models)

    svc = AIService(api_key="k", modelos=["m"], client_factory=factory)
    svc.analisar(DADOS)
    svc.analisar(DADOS)
    assert criados == ["k"]


def test_prompt_contem_indicadores():
    p = montar_prompt(DADOS)
    for trecho in ("BTC/USDT", "15m", "RSI(14): 55.0", "Veredito", "português"):
        assert trecho in p


@pytest.mark.parametrize(
    "ajuste, veredito",
    [
        ({"rsi": 20}, "COMPRA"),
        ({"rsi": 80}, "VENDA"),
        ({"preco": 110, "ema9": 105, "ema21": 100}, "COMPRA"),
        ({"preco": 90, "ema9": 95, "ema21": 100}, "VENDA"),
        ({"preco": 110, "ema9": 95, "ema21": 100}, "NEUTRO"),
    ],
)
def test_analise_offline(ajuste, veredito):
    res = analise_offline({**DADOS, **ajuste}, "teste")
    assert f"**Veredito:** {veredito}" in res.texto
    assert res.offline and "teste" in res.texto


def test_modelos_configuraveis(monkeypatch):
    assert modelos_configurados() == ai.MODELOS_PADRAO
    monkeypatch.setenv("GEMINI_MODELS", " a , b,, ")
    assert modelos_configurados() == ["a", "b"]


def test_ler_api_key_do_ambiente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  abc ")
    assert ai.ler_api_key() == "abc"

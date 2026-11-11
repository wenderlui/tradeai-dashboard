"""Análise por IA (Google Gemini) com rotação de modelos e fallback local."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .indicators import formatar_preco, zona_rsi

log = logging.getLogger(__name__)

MODELOS_PADRAO = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

AVISO_LEGAL = "_Conteúdo educativo. Não é recomendação de investimento._"


@dataclass
class Analise:
    texto: str
    modelo: str
    offline: bool = False
    motivo: str = ""


def modelos_configurados() -> list[str]:
    """Permite trocar os modelos sem mexer no código: GEMINI_MODELS=modelo1,modelo2."""
    bruto = os.getenv("GEMINI_MODELS", "")
    modelos = [m.strip() for m in bruto.split(",") if m.strip()]
    return modelos or list(MODELOS_PADRAO)


def ler_api_key() -> str | None:
    chave = os.getenv("GEMINI_API_KEY")
    if chave:
        return chave.strip() or None
    try:
        import streamlit as st

        chave = st.secrets.get("GEMINI_API_KEY")
    except Exception:  # sem secrets.toml
        chave = None
    return (chave or "").strip() or None


def montar_prompt(dados: dict[str, Any]) -> str:
    return f"""Você é um analista técnico de criptomoedas. Responda em português do Brasil, em Markdown, de forma objetiva (máx. 120 palavras).

Ativo: {dados["simbolo"]} | Tempo gráfico: {dados["timeframe"]} | Fonte: {dados.get("exchange", "-")}
Preço: {formatar_preco(dados["preco"])} | Variação no período: {dados.get("variacao", 0):+.2f}%
RSI(14): {dados["rsi"]:.1f} | EMA9: {formatar_preco(dados["ema9"])} | EMA21: {formatar_preco(dados["ema21"])}
Máxima recente: {formatar_preco(dados.get("maxima", 0))} | Mínima recente: {formatar_preco(dados.get("minima", 0))}
Score técnico (0-100): {dados.get("score", 50)} ({dados.get("tendencia", "Neutro")})

Formato obrigatório:
**Veredito:** COMPRA, VENDA ou NEUTRO
- 2 ou 3 tópicos curtos justificando com os indicadores acima
- **Suporte / Resistência:** valores
- **Risco:** uma frase
"""


def _erro_definitivo(msg: str) -> bool:
    """Erros de autenticação não melhoram trocando de modelo."""
    m = msg.lower()
    return any(t in m for t in ("api key not valid", "api_key_invalid", "permission_denied", "401", "403"))


def _resumir_erro(exc: Exception) -> str:
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "cota excedida (429)"
    if "404" in msg or "NOT_FOUND" in msg:
        return "modelo indisponível (404)"
    if _erro_definitivo(msg):
        return "chave de API inválida ou sem permissão"
    return msg.splitlines()[0][:160] if msg else type(exc).__name__


def _cliente_gemini(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


class AIService:
    def __init__(
        self,
        api_key: str | None = None,
        modelos: list[str] | None = None,
        client_factory: Callable[[str], Any] = _cliente_gemini,
        espera_entre_tentativas: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key if api_key is not None else ler_api_key()
        self.modelos = modelos or modelos_configurados()
        self._client_factory = client_factory
        self._espera = espera_entre_tentativas
        self._sleep = sleep
        self._client = None

    @property
    def configurada(self) -> bool:
        return bool(self.api_key)

    def analisar(self, dados: dict[str, Any]) -> Analise:
        if not dados.get("preco"):
            return Analise("⚠️ Sem dados de mercado para analisar.", "—", offline=True, motivo="sem dados")
        if not self.api_key:
            return analise_offline(dados, "chave GEMINI_API_KEY não configurada")

        prompt = montar_prompt(dados)
        ultimo_erro = ""
        try:
            if self._client is None:
                self._client = self._client_factory(self.api_key)
        except Exception as exc:
            return analise_offline(dados, f"falha ao iniciar o Gemini: {_resumir_erro(exc)}")

        for i, modelo in enumerate(self.modelos):
            try:
                resposta = self._client.models.generate_content(model=modelo, contents=prompt)
                texto = (getattr(resposta, "text", None) or "").strip()
                if not texto:
                    raise ValueError("resposta vazia")
                return Analise(texto, modelo)
            except Exception as exc:
                ultimo_erro = _resumir_erro(exc)
                log.warning("Modelo %s falhou: %s", modelo, ultimo_erro)
                if _erro_definitivo(str(exc)):
                    break
                if i < len(self.modelos) - 1 and self._espera:
                    self._sleep(self._espera)

        return analise_offline(dados, f"IA indisponível ({ultimo_erro})")


def analise_offline(dados: dict[str, Any], motivo: str) -> Analise:
    """Análise determinística usada quando o Gemini não está disponível."""
    rsi = float(dados["rsi"])
    preco = float(dados["preco"])
    ema21 = float(dados["ema21"])
    ema9 = float(dados.get("ema9", ema21))

    if rsi < 30:
        veredito = "COMPRA"
    elif rsi > 70:
        veredito = "VENDA"
    elif preco > ema21 and ema9 >= ema21:
        veredito = "COMPRA"
    elif preco < ema21 and ema9 <= ema21:
        veredito = "VENDA"
    else:
        veredito = "NEUTRO"

    lado = "acima" if preco >= ema21 else "abaixo"
    cruzamento = "acima" if ema9 >= ema21 else "abaixo"
    linhas = [
        f"**Veredito:** {veredito}",
        f"- RSI(14) em {rsi:.1f} ({zona_rsi(rsi).lower()}).",
        f"- Preço {lado} da EMA21 ({formatar_preco(ema21)}).",
        f"- EMA9 {cruzamento} da EMA21.",
    ]
    if dados.get("minima") and dados.get("maxima"):
        linhas.append(
            f"- **Suporte / Resistência:** {formatar_preco(dados['minima'])} / {formatar_preco(dados['maxima'])}"
        )
    linhas.append("")
    linhas.append(f"_Análise matemática local — {motivo}._")
    return Analise("\n".join(linhas), "Análise local", offline=True, motivo=motivo)

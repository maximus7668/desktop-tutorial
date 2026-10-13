"""Agentes macro: noticias/sentimiento y relaciones intermarket (correlación entre futuros)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from propfut.agents.base import Agent, AgentSignal, MarketContext, clip01, finite
from propfut.data.news import Impact
from propfut.regime.detector import Regime

R = Regime


class MacroNewsAgent(Agent):
    """Gestiona el riesgo de eventos y aporta sesgo direccional de sentimiento.

    * Emite ``veto`` durante blackout y en los minutos previos a un evento de alto
      impacto (defensa en profundidad: el RiskEngine también lo comprueba).
    * Si hay un proveedor de sentimiento, aporta una señal suave en su dirección.
    """

    name = "macro_news"
    default_affinity = {R.TREND_UP: 0.5, R.TREND_DOWN: 0.5, R.RANGE: 0.4, R.SQUEEZE: 0.4,
                        R.HIGH_VOL: 0.5, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        n = ctx.news
        if n.in_blackout:
            title = n.event.title if n.event else "evento"
            return AgentSignal(self.name, ctx.root, ctx.ts, 0.0, 0.0, 1, veto=True,
                               explanation=f"Blackout de noticias: {title}")
        pre = float(self.p("pre_event_minutes", 15))
        if n.minutes_to_next is not None and 0 <= n.minutes_to_next <= pre:
            return AgentSignal(self.name, ctx.root, ctx.ts, 0.0, 0.0, 1, veto=True,
                               explanation=f"Evento macro en {n.minutes_to_next:.0f} min: no abrir riesgo")
        s = n.sentiment
        if s is not None and math.isfinite(s) and abs(s) >= float(self.p("min_sentiment", 0.3)):
            conf = 0.25 + 0.35 * clip01((abs(s) - 0.3) / 0.7)
            return self.signal(ctx, float(np.sign(s)), conf, 24, None, None,
                               f"Sesgo de sentimiento macro {s:+.2f}")
        if n.minutes_since_last is not None and n.minutes_since_last < 120 and n.last_impact is Impact.HIGH:
            return self.neutral(ctx, "post-noticia: sin sesgo fiable")
        return self.neutral(ctx)


class IntermarketAgent(Agent):
    """Reversión del residuo de una relación estable entre futuros correlacionados.

    Para cada raíz de referencia (p.ej. NQ para ES, CL para NG...): estima beta y
    correlación en una ventana rodante; si la correlación es alta y el residuo
    acumulado reciente es extremo (|z| > umbral), apuesta a su cierre. Si la
    correlación se rompe, no opina (posible cambio de régimen).
    """

    name = "intermarket"
    default_affinity = {R.RANGE: 0.9, R.TREND_UP: 0.5, R.TREND_DOWN: 0.5, R.SQUEEZE: 0.5,
                        R.HIGH_VOL: 0.3, R.NEWS_DRIVEN: 0.0}

    def __init__(self, params: dict[str, Any] | None = None, references: list[str] | None = None) -> None:
        super().__init__(params)
        self.references = references or []

    def generate(self, ctx: MarketContext) -> AgentSignal:
        refs = [r for r in self.references if r in ctx.peers]
        if not refs:
            return self.neutral(ctx, "sin referencias intermarket")
        win = int(self.p("window", 120))
        k = int(self.p("residual_bars", 12))
        z_th = float(self.p("z_threshold", 2.0))
        min_rho = float(self.p("min_correlation", 0.6))
        best: AgentSignal | None = None
        for ref in refs:
            frame, j = ctx.peers[ref]
            if j < win or ctx.i < win:
                continue
            if frame.index[j] != ctx.frame.index[ctx.i] or frame.index[j - win + 1] != ctx.frame.index[ctx.i - win + 1]:
                continue  # rejillas temporales no alineadas: no arriesgar
            y = ctx.hist("ret", win)
            x = frame.window("ret", j, win)
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < win * 0.9:
                continue
            xv, yv = x[ok], y[ok]
            vx = xv.var()
            if vx <= 0:
                continue
            beta = float(np.cov(xv, yv, bias=True)[0, 1] / vx)
            rho = float(np.corrcoef(xv, yv)[0, 1])
            if not finite(beta, rho) or rho < min_rho:
                continue
            resid = yv - beta * xv
            sd = resid[:-k].std() if len(resid) > 2 * k else resid.std()
            if sd <= 0:
                continue
            z = float(resid[-k:].sum() / (sd * math.sqrt(k)))
            if abs(z) > z_th:
                conf = (0.3 + 0.4 * clip01((abs(z) - z_th) / 2.0)) * clip01((rho - 0.4) / 0.5)
                sig = self.signal(ctx, -float(np.sign(z)), conf, k, 1.2, 1.8,
                                  f"Residuo vs {ref} z={z:+.2f} (beta={beta:.2f}, rho={rho:.2f}) -> reversión",
                                  z=z, beta=beta, rho=rho)
                if best is None or sig.confidence > best.confidence:
                    best = sig
        return best or self.neutral(ctx)

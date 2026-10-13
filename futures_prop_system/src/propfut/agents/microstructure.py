"""Agentes de microestructura: order flow (delta / CVD) y volume profile + auction theory."""

from __future__ import annotations

import numpy as np

from propfut.agents.base import Agent, AgentSignal, MarketContext, clip01, finite
from propfut.regime.detector import Regime

R = Regime


class OrderFlowAgent(Agent):
    """Divergencias precio/CVD (absorción) e imbalances agresivos de continuación.

    Con datos sin lado agresor (``delta_estimated``=1) el delta se estima con la
    posición del cierre en el rango (CLV) y la confianza se reduce a la mitad:
    el order flow real requiere datos de tick con bid/ask.
    """

    name = "order_flow"
    default_affinity = {R.RANGE: 0.8, R.TREND_UP: 0.8, R.TREND_DOWN: 0.8, R.SQUEEZE: 0.7,
                        R.HIGH_VOL: 0.5, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        pc, cvd, dz = ctx.f("price_chg_atr"), ctx.f("cvd_chg_norm"), ctx.f("delta_z")
        h, lo, c, vwap = ctx.f("high"), ctx.f("low"), ctx.f("close"), ctx.f("vwap")
        if not finite(pc, cvd, dz, h, lo, c, vwap):
            return self.neutral(ctx, "warm-up")
        quality = 0.5 if ctx.f("delta_estimated") >= 1 else 1.0
        div_px = float(self.p("divergence_price_atr", 1.2))
        div_cvd = float(self.p("divergence_cvd", 0.05))
        if pc > div_px and cvd < -div_cvd:
            conf = (0.35 + 0.35 * clip01((pc - div_px) / 1.5) + 0.3 * clip01((-cvd - div_cvd) / 0.2)) * quality
            return self.signal(ctx, -1.0, conf, 8, 1.2, 2.0,
                               f"Divergencia bajista: precio +{pc:.2f}ATR con CVD {cvd:+.2f} (absorción)")
        if pc < -div_px and cvd > div_cvd:
            conf = (0.35 + 0.35 * clip01((-pc - div_px) / 1.5) + 0.3 * clip01((cvd - div_cvd) / 0.2)) * quality
            return self.signal(ctx, 1.0, conf, 8, 1.2, 2.0,
                               f"Divergencia alcista: precio {pc:.2f}ATR con CVD {cvd:+.2f} (absorción)")
        rng = h - lo
        if rng > 0 and abs(dz) > float(self.p("imbalance_z", 2.0)):
            pos = (c - lo) / rng
            if dz > 0 and pos > 0.75 and c > vwap:
                return self.signal(ctx, 1.0, (0.3 + 0.3 * clip01((dz - 2) / 2)) * quality, 6, 1.0, 2.0,
                                   f"Imbalance comprador z={dz:.1f}, cierre en máximos sobre VWAP")
            if dz < 0 and pos < 0.25 and c < vwap:
                return self.signal(ctx, -1.0, (0.3 + 0.3 * clip01((-dz - 2) / 2)) * quality, 6, 1.0, 2.0,
                                   f"Imbalance vendedor z={dz:.1f}, cierre en mínimos bajo VWAP")
        return self.neutral(ctx)


class AuctionAgent(Agent):
    """Volume profile + teoría de subastas sobre el value area de la sesión previa.

    * Regla del 80 %: apertura fuera de value y re-entrada aceptada (2 cierres
      dentro) -> objetivo el extremo opuesto del value area.
    * Subasta fallida: sondeo fuera de value rechazado con delta en contra -> POC.
    * Aceptación fuera de value: N cierres consecutivos fuera -> continuación.
    """

    name = "auction"
    default_affinity = {R.RANGE: 1.0, R.TREND_UP: 0.6, R.TREND_DOWN: 0.6, R.SQUEEZE: 0.6,
                        R.HIGH_VOL: 0.3, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        vah, val, poc = ctx.f("prev_vah"), ctx.f("prev_val"), ctx.f("prev_poc")
        c, h, lo, atr = ctx.f("close"), ctx.f("high"), ctx.f("low"), ctx.f("atr")
        op, ms = ctx.f("rth_open_price"), ctx.f("mins_since_rth_open")
        if not finite(vah, val, poc, c, h, lo, atr, op, ms) or atr <= 0 or vah <= val:
            return self.neutral(ctx, "sin perfil previo o fuera de RTH")
        closes = ctx.hist("close", 3)
        if len(closes) < 3:
            return self.neutral(ctx)
        inside = (closes >= val) & (closes <= vah)

        # regla del 80 %
        if ms >= 30 and inside[-1] and inside[-2]:
            if op > vah and closes[-3] > vah:
                tgt = (c - val) / atr
                if tgt >= 1.0:
                    return self.signal(ctx, -1.0, 0.55, 18, 1.2, tgt,
                                       f"Regla 80%: abrió sobre VAH {vah:.2f} y re-entró en value -> VAL {val:.2f}")
            if op < val and closes[-3] < val:
                tgt = (vah - c) / atr
                if tgt >= 1.0:
                    return self.signal(ctx, 1.0, 0.55, 18, 1.2, tgt,
                                       f"Regla 80%: abrió bajo VAL {val:.2f} y re-entró en value -> VAH {vah:.2f}")

        dlt = ctx.f("delta")
        # subasta fallida en extremos
        if h > vah >= c and finite(dlt) and dlt < 0 and (c - poc) / atr > 0.8:
            return self.signal(ctx, -1.0, 0.45, 10, 1.0, (c - poc) / atr,
                               f"Subasta fallida sobre VAH {vah:.2f}: rechazo con delta negativo -> POC")
        if lo < val <= c and finite(dlt) and dlt > 0 and (poc - c) / atr > 0.8:
            return self.signal(ctx, 1.0, 0.45, 10, 1.0, (poc - c) / atr,
                               f"Subasta fallida bajo VAL {val:.2f}: rechazo con delta positivo -> POC")

        n = int(self.p("acceptance_bars", 3))
        last = ctx.hist("close", n)
        if len(last) == n and val <= op <= vah:
            if np.all(last > vah) and (c - vah) / atr < 1.0:
                return self.signal(ctx, 1.0, 0.4, 16, 1.3, 2.6,
                                   f"Aceptación sobre value ({n} cierres > VAH {vah:.2f})")
            if np.all(last < val) and (val - c) / atr < 1.0:
                return self.signal(ctx, -1.0, 0.4, 16, 1.3, 2.6,
                                   f"Aceptación bajo value ({n} cierres < VAL {val:.2f})")
        return self.neutral(ctx)

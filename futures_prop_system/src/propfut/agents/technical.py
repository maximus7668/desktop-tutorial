"""Agentes de precio: tendencia/momentum, mean-reversion y expansión de volatilidad."""

from __future__ import annotations

import numpy as np

from propfut.agents.base import Agent, AgentSignal, MarketContext, clip01, finite
from propfut.regime.detector import Regime

R = Regime


class TrendMomentumAgent(Agent):
    """Breakouts de Donchian con filtro de eficiencia y continuaciones en pullback a la EMA."""

    name = "trend"
    default_affinity = {R.TREND_UP: 1.0, R.TREND_DOWN: 1.0, R.SQUEEZE: 0.6, R.RANGE: 0.15,
                        R.HIGH_VOL: 0.4, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        c, atr = ctx.f("close"), ctx.f("atr")
        dh, dl, er = ctx.f("donchian_high"), ctx.f("donchian_low"), ctx.f("er")
        spread, slope, ema_f = ctx.f("ema_spread_atr"), ctx.f("ema_slope_atr"), ctx.f("ema_fast")
        vrel = ctx.f("volume_rel_tod")
        if not finite(c, atr, dh, dl, er, spread, slope, ema_f) or atr <= 0:
            return self.neutral(ctx, "warm-up")
        min_er = float(self.p("min_er", 0.30))
        buf = float(self.p("breakout_buffer_atr", 0.05)) * atr
        vol_boost = clip01(((vrel if finite(vrel) else 1.0) - 1.0) / 1.5)
        er_q = clip01((er - min_er) / 0.4)

        if c > dh + buf and spread > 0 and er >= min_er:
            conf = 0.35 + 0.35 * er_q + 0.3 * vol_boost
            return self.signal(ctx, 1.0, conf, 12, 1.5, 3.0,
                               f"Breakout alcista Donchian ({c:.2f} > {dh:.2f}), ER={er:.2f}", er=er)
        if c < dl - buf and spread < 0 and er >= min_er:
            conf = 0.35 + 0.35 * er_q + 0.3 * vol_boost
            return self.signal(ctx, -1.0, conf, 12, 1.5, 3.0,
                               f"Breakout bajista Donchian ({c:.2f} < {dl:.2f}), ER={er:.2f}", er=er)

        # continuación: tendencia establecida + pullback a la EMA rápida
        dist = (c - ema_f) / atr
        if abs(spread) > 0.8 and np.sign(slope) == np.sign(spread) and abs(dist) < 0.3:
            closes = ctx.hist("close", 4)
            if len(closes) == 4:
                resumed = (closes[-1] - closes[-2]) * np.sign(spread) > 0
                if resumed:
                    d = float(np.sign(spread))
                    conf = 0.30 + 0.3 * clip01((abs(spread) - 0.8) / 1.5) + 0.2 * er_q
                    return self.signal(ctx, d, conf, 10, 1.3, 2.6,
                                       f"Continuación en pullback a EMA (spread={spread:+.2f} ATR)")
        return self.neutral(ctx)


class MeanReversionAgent(Agent):
    """Fade de extensiones (Bollinger z + distancia a VWAP) sólo en mercados no direccionales."""

    name = "mean_reversion"
    default_affinity = {R.RANGE: 1.0, R.SQUEEZE: 0.3, R.TREND_UP: 0.15, R.TREND_DOWN: 0.15,
                        R.HIGH_VOL: 0.3, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        z, vd, er, atr = ctx.f("bb_z"), ctx.f("vwap_dist_atr"), ctx.f("er"), ctx.f("atr")
        if not finite(z, vd, er, atr) or atr <= 0:
            return self.neutral(ctx, "warm-up")
        if er > float(self.p("max_er", 0.30)):
            return self.neutral(ctx, f"mercado direccional (ER={er:.2f})")
        z_th = float(self.p("z_threshold", 2.0))
        zs = ctx.hist("bb_z", 2)
        if len(zs) < 2 or not np.isfinite(zs).all():
            return self.neutral(ctx)
        # confirmación: la extensión ya empieza a revertir (z se aleja del extremo)
        if zs[-2] > z_th and z < zs[-2] and vd > 1.0:
            conf = 0.3 + 0.4 * clip01((zs[-2] - z_th) / 1.5) + 0.3 * clip01((vd - 1.0) / 1.5)
            return self.signal(ctx, -1.0, conf, 8, 1.2, max(1.0, vd),
                               f"Fade de extensión alcista: z={zs[-2]:.2f}->{z:.2f}, VWAP+{vd:.2f}ATR")
        if zs[-2] < -z_th and z > zs[-2] and vd < -1.0:
            conf = 0.3 + 0.4 * clip01((-zs[-2] - z_th) / 1.5) + 0.3 * clip01((-vd - 1.0) / 1.5)
            return self.signal(ctx, 1.0, conf, 8, 1.2, max(1.0, -vd),
                               f"Fade de extensión bajista: z={zs[-2]:.2f}->{z:.2f}, VWAP{vd:.2f}ATR")
        return self.neutral(ctx)


class VolatilityExpansionAgent(Agent):
    """Ruptura tras compresión (squeeze release) y opening-range breakout en RTH."""

    name = "volatility"
    default_affinity = {R.SQUEEZE: 1.0, R.TREND_UP: 0.6, R.TREND_DOWN: 0.6, R.HIGH_VOL: 0.4,
                        R.RANGE: 0.3, R.NEWS_DRIVEN: 0.0}

    def generate(self, ctx: MarketContext) -> AgentSignal:
        o, c, atr = ctx.f("open"), ctx.f("close"), ctx.f("atr")
        rng, vrel = ctx.f("range_rel_tod"), ctx.f("volume_rel_tod")
        if not finite(o, c, atr, rng, vrel) or atr <= 0:
            return self.neutral(ctx, "warm-up")
        sq = ctx.hist("squeeze_ratio", int(self.p("squeeze_lookback", 12)))
        was_squeezed = len(sq) > 2 and np.nanmin(sq[:-1]) < 1.0
        exp_th = float(self.p("expansion_rel_tod", 2.0))
        if was_squeezed and rng > exp_th and vrel > 1.5 and c != o:
            d = float(np.sign(c - o))
            conf = 0.35 + 0.35 * clip01((rng - exp_th) / 2.0) + 0.3 * clip01((vrel - 1.5) / 2.0)
            return self.signal(ctx, d, conf, 10, 1.2, 2.5,
                               f"Squeeze release: rango {rng:.2f}x el típico de esta hora, volumen {vrel:.1f}x")

        orh, orl, ms = ctx.f("or_high"), ctx.f("or_low"), ctx.f("mins_since_rth_open")
        if finite(orh, orl, ms) and ms <= float(self.p("orb_window_minutes", 120)):
            width = (orh - orl) / atr
            closes = ctx.hist("close", 2)
            if len(closes) == 2 and 0.5 < width < 4.0:
                mid = 0.5 * (orh + orl)
                if closes[0] <= orh < c:
                    stop = max(0.8, (c - mid) / atr)  # stop en la mitad del OR
                    return self.signal(ctx, 1.0, 0.45 + 0.2 * clip01(vrel - 1), 12, stop, 2.0 * stop,
                                       f"Opening range breakout alcista (OR {orl:.2f}-{orh:.2f})")
                if closes[0] >= orl > c:
                    stop = max(0.8, (mid - c) / atr)
                    return self.signal(ctx, -1.0, 0.45 + 0.2 * clip01(vrel - 1), 12, stop, 2.0 * stop,
                                       f"Opening range breakout bajista (OR {orl:.2f}-{orh:.2f})")
        return self.neutral(ctx)

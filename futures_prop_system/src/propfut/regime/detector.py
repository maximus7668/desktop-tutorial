"""Motor de detección de régimen adaptado a futuros.

Combina medidas robustas y explicables (efficiency ratio, pendiente/spread de
EMAs normalizado por ATR, percentil de ATR, compresión Bollinger/Keltner) con un
HMM de volatilidad filtrado causalmente, y aplica histéresis para evitar
"parpadeo" de régimen. El resultado modula:

* la ponderación de agentes en el ensemble (afinidades por régimen), y
* el sizing (``risk_multiplier``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from propfut.core.config import RegimeConfig
from propfut.data.news import Impact, NewsState
from propfut.regime.hmm import GaussianHMM


class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    SQUEEZE = "SQUEEZE"
    NEWS_DRIVEN = "NEWS_DRIVEN"
    UNKNOWN = "UNKNOWN"

    @property
    def is_trend(self) -> bool:
        return self in (Regime.TREND_UP, Regime.TREND_DOWN)


@dataclass(frozen=True, slots=True)
class RegimeState:
    label: Regime
    probs: Mapping[Regime, float]
    confidence: float
    risk_multiplier: float
    vol_state: str  # "low" | "normal" | "high"
    explanation: str
    scores: Mapping[str, float] = field(default_factory=dict)

    def p(self, r: Regime) -> float:
        return float(self.probs.get(r, 0.0))

    @classmethod
    def unknown(cls, reason: str) -> "RegimeState":
        return cls(Regime.UNKNOWN, {Regime.UNKNOWN: 1.0}, 0.0, 0.0, "normal", reason)


def _sig(x: float) -> float:
    if x > 40:
        return 1.0
    if x < -40:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class _RootState:
    label: Regime = Regime.UNKNOWN
    candidate: Regime | None = None
    count: int = 0
    hmm_probs: np.ndarray | None = None


class RegimeDetector:
    REQUIRED = ("er", "ema_spread_atr", "ema_slope_atr", "atr_rank", "bb_width_rank", "squeeze_ratio")

    def __init__(self, cfg: RegimeConfig | None = None) -> None:
        self.cfg = cfg or RegimeConfig()
        self._state: dict[str, _RootState] = {}
        self._hmm: dict[str, GaussianHMM] = {}

    # ------------------------------------------------------------------ #
    def fit_hmm(self, root: str, rv_series: np.ndarray) -> None:
        """Ajusta el HMM de volatilidad con datos de ENTRENAMIENTO (nunca con el periodo de test)."""
        x = np.log(np.asarray(rv_series, dtype=float))
        x = x[np.isfinite(x)]
        if len(x) >= 200:
            self._hmm[root] = GaussianHMM(self.cfg.hmm_states).fit(x)

    def reset(self, root: str | None = None) -> None:
        if root is None:
            self._state.clear()
        else:
            self._state.pop(root, None)

    # ------------------------------------------------------------------ #
    def classify(self, root: str, row: Mapping[str, float], news: NewsState | None = None) -> RegimeState:
        st = self._state.setdefault(root, _RootState())
        cfg = self.cfg

        # filtrado HMM (siempre, para mantener el estado aunque falten otras features)
        p_hmm_high: float | None = None
        hmm = self._hmm.get(root) if cfg.use_hmm else None
        rv = row.get("rv", float("nan"))
        if hmm is not None and hmm.fitted and rv > 0 and math.isfinite(rv):
            st.hmm_probs = hmm.filter_step(st.hmm_probs, math.log(rv))
            p_hmm_high = float(st.hmm_probs[-1])

        if news is not None and (
            news.in_blackout
            or (
                news.minutes_since_last is not None
                and news.minutes_since_last < 30
                and news.last_impact is Impact.HIGH
            )
        ):
            st.label, st.candidate, st.count = Regime.NEWS_DRIVEN, None, 0
            title = news.event.title if news.event else "evento reciente"
            return RegimeState(
                Regime.NEWS_DRIVEN, {Regime.NEWS_DRIVEN: 1.0}, 1.0,
                cfg.risk_multipliers.get("NEWS_DRIVEN", 0.0), "high", f"Ventana de noticias: {title}",
            )

        vals = {k: row.get(k, float("nan")) for k in self.REQUIRED}
        if any(not math.isfinite(v) for v in vals.values()):
            st.label = Regime.UNKNOWN
            return RegimeState.unknown("Warm-up: features insuficientes")

        er, spread, slope = vals["er"], vals["ema_spread_atr"], vals["ema_slope_atr"]
        atr_rank, bbw_rank, sq = vals["atr_rank"], vals["bb_width_rank"], vals["squeeze_ratio"]

        high_rank = _sig((atr_rank - cfg.high_vol_percentile) / 0.04)
        high = high_rank if p_hmm_high is None else 0.5 * high_rank + 0.5 * p_hmm_high
        trend = _sig((er - cfg.trend_er_threshold) / 0.07) * _sig((abs(spread) - 0.5) / 0.25)
        trend *= 0.5 + 0.5 * _sig(slope * np.sign(spread) / 0.05)  # pendiente coherente
        rng = _sig((cfg.range_er_threshold - er) / 0.07) * (1 - high)
        squeeze = _sig((cfg.squeeze_percentile - bbw_rank) / 0.04) * _sig((1.0 - sq) / 0.1) * (1 - high)

        trend_label = Regime.TREND_UP if spread > 0 else Regime.TREND_DOWN
        raw = {trend_label: trend, Regime.RANGE: rng, Regime.HIGH_VOL: high, Regime.SQUEEZE: squeeze}
        total = sum(raw.values()) + 1e-9
        probs = {r: v / total for r, v in raw.items()}
        top = max(probs, key=lambda r: probs[r])

        # histéresis
        if st.label in (Regime.UNKNOWN, Regime.NEWS_DRIVEN) or top == st.label:
            st.label, st.candidate, st.count = top, None, 0
        else:
            if st.candidate == top:
                st.count += 1
            else:
                st.candidate, st.count = top, 1
            if st.count >= cfg.hysteresis_bars or probs[top] > 0.75:
                st.label, st.candidate, st.count = top, None, 0
        label = st.label
        if label not in probs:  # p.ej. TREND_UP -> TREND_DOWN directo
            label = st.label = top

        mult = sum(p * cfg.risk_multipliers.get(r.value, 0.5) for r, p in probs.items())
        mult = min(mult, cfg.risk_multipliers.get(label.value, 1.0) + 0.1)
        vol_state = "high" if high > 0.5 else ("low" if atr_rank < 0.25 else "normal")
        expl = (
            f"{label.value} (p={probs[label]:.2f}) | ER={er:.2f} spread={spread:+.2f}ATR "
            f"ATR%={atr_rank:.2f} BBW%={bbw_rank:.2f}"
            + (f" HMM_high={p_hmm_high:.2f}" if p_hmm_high is not None else "")
        )
        return RegimeState(
            label, probs, probs[label], float(np.clip(mult, 0.0, 1.0)), vol_state, expl,
            {"er": er, "spread": spread, "atr_rank": atr_rank, "bbw_rank": bbw_rank, "high": high},
        )

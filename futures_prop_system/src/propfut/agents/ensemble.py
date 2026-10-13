"""Ensemble dinámico de agentes.

peso_i = peso_base_i x afinidad_i(P(régimen)) x factor_rendimiento_i

* La **afinidad** es la esperanza de la afinidad del agente bajo la distribución
  de probabilidad del régimen actual.
* El **factor de rendimiento** se calcula con señales ya *resueltas* (su
  horizonte ha vencido): no hay look-ahead. Se encoge hacia 1 con pocas muestras
  y se acota en [0.25, 2] para que ningún agente domine ni desaparezca del todo.
* Cualquier ``veto`` de un agente bloquea la decisión (el RiskEngine decide igualmente).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from propfut.agents.base import Agent, AgentSignal
from propfut.core.config import EnsembleConfig
from propfut.regime.detector import RegimeState


@dataclass(frozen=True, slots=True)
class Contribution:
    agent: str
    weight: float
    direction: float
    confidence: float
    affinity: float
    performance: float
    explanation: str

    @property
    def strength(self) -> float:
        return self.weight * self.direction * self.confidence


@dataclass(frozen=True)
class EnsembleDecision:
    root: str
    ts: datetime
    score: float  # [-1, 1]
    direction: int  # -1, 0, 1 (0 = no operar)
    confidence: float
    agreement: float
    stop_atr: float
    target_atr: float
    horizon_bars: int
    regime: RegimeState
    contributions: Sequence[Contribution] = field(default_factory=tuple)
    blocked: bool = False
    block_reasons: Sequence[str] = field(default_factory=tuple)

    @property
    def actionable(self) -> bool:
        return self.direction != 0 and not self.blocked

    def explain(self) -> str:
        parts = [f"{c.agent}:{c.direction * c.confidence:+.2f}(w={c.weight:.2f})" for c in self.contributions]
        status = "BLOQUEADO: " + "; ".join(self.block_reasons) if self.blocked else (
            "LARGO" if self.direction > 0 else "CORTO" if self.direction < 0 else "SIN OPERACIÓN"
        )
        return (f"{status} score={self.score:+.2f} conf={self.confidence:.2f} agree={self.agreement:.2f} "
                f"| régimen {self.regime.label.value} | " + ", ".join(parts))


@dataclass
class _Pending:
    agent: str
    direction: float
    confidence: float
    entry_price: float
    atr: float
    due_index: int


class PerformanceTracker:
    """Rendimiento online de cada agente medido en ATRs a su horizonte declarado."""

    def __init__(self, halflife: int = 40, min_samples: int = 20, sensitivity: float = 1.5) -> None:
        self.alpha = 1.0 - 0.5 ** (1.0 / halflife)
        self.min_samples = min_samples
        self.sensitivity = sensitivity
        self._pending: dict[str, list[_Pending]] = defaultdict(list)
        self._mean: dict[str, float] = defaultdict(float)
        self._hit: dict[str, float] = defaultdict(lambda: 0.5)
        self._n: dict[str, int] = defaultdict(int)

    def record(self, root: str, sig: AgentSignal, i: int, price: float, atr: float) -> None:
        if sig.is_neutral or not (atr > 0 and math.isfinite(price)):
            return
        self._pending[root].append(
            _Pending(sig.agent, sig.direction, sig.confidence, price, atr, i + max(1, sig.horizon_bars))
        )

    def resolve(self, root: str, i: int, price: float) -> None:
        if not math.isfinite(price):
            return
        keep: list[_Pending] = []
        for p in self._pending[root]:
            if p.due_index > i:
                keep.append(p)
                continue
            x = float(np.clip(p.direction * (price - p.entry_price) / p.atr, -3.0, 3.0))
            a = self.alpha
            self._mean[p.agent] = (1 - a) * self._mean[p.agent] + a * x
            self._hit[p.agent] = (1 - a) * self._hit[p.agent] + a * (1.0 if x > 0 else 0.0)
            self._n[p.agent] += 1
        self._pending[root] = keep

    def factor(self, agent: str) -> float:
        n = self._n[agent]
        shrink = min(1.0, n / self.min_samples)
        return float(np.clip(1.0 + self.sensitivity * self._mean[agent] * shrink, 0.25, 2.0))

    def stats(self) -> dict[str, dict[str, float]]:
        return {
            a: {"n": float(self._n[a]), "ew_mean_atr": self._mean[a], "ew_hit_rate": self._hit[a],
                "factor": self.factor(a)}
            for a in self._n
        }


class DynamicEnsemble:
    def __init__(
        self,
        agents: Sequence[Agent],
        cfg: EnsembleConfig | None = None,
        base_weights: Mapping[str, float] | None = None,
        neutral_dilution: float = 0.25,
    ) -> None:
        self.agents = list(agents)
        self.cfg = cfg or EnsembleConfig()
        self.base_weights = dict(base_weights or {})
        self.neutral_dilution = neutral_dilution
        self.tracker = PerformanceTracker(
            self.cfg.performance_halflife, self.cfg.performance_min_samples, self.cfg.performance_sensitivity
        )
        self._by_name = {a.name: a for a in self.agents}

    def combine(
        self, root: str, ts: datetime, signals: Sequence[AgentSignal], regime: RegimeState
    ) -> EnsembleDecision:
        cfg = self.cfg
        vetoes = [s.explanation for s in signals if s.veto]
        contribs: list[Contribution] = []
        active_w = neutral_w = 0.0
        for s in signals:
            agent = self._by_name.get(s.agent)
            aff = agent.affinity(regime) if agent else 0.5
            perf = self.tracker.factor(s.agent)
            w = self.base_weights.get(s.agent, 1.0) * aff * perf
            if s.is_neutral:
                neutral_w += w
                continue
            active_w += w
            contribs.append(Contribution(s.agent, w, s.direction, s.confidence, aff, perf, s.explanation))

        denom = active_w + self.neutral_dilution * neutral_w
        score = sum(c.strength for c in contribs) / denom if denom > 0 else 0.0
        mass = sum(c.weight * c.confidence for c in contribs)
        agree = (
            sum(c.weight * c.confidence for c in contribs if np.sign(c.direction) == np.sign(score)) / mass
            if mass > 0 and score != 0 else 0.0
        )
        conf = abs(score)
        direction = int(np.sign(score)) if conf >= cfg.min_confidence and agree >= cfg.min_agreement else 0

        # stop/target/horizonte: media ponderada de los agentes alineados
        aligned = [c for c in contribs if np.sign(c.direction) == np.sign(score)]
        sigs = {s.agent: s for s in signals}
        def wavg(attr: str, default: float) -> float:
            vals = [(c.weight * c.confidence, getattr(sigs[c.agent], attr)) for c in aligned]
            vals = [(w, v) for w, v in vals if v is not None and math.isfinite(v) and v > 0]
            tw = sum(w for w, _ in vals)
            return sum(w * v for w, v in vals) / tw if tw > 0 else default
        stop_atr = wavg("stop_atr", cfg.default_stop_atr)
        target_atr = wavg("target_atr", cfg.default_stop_atr * cfg.default_target_rr)
        horizon = int(round(wavg("horizon_bars", 12)))

        return EnsembleDecision(
            root=root, ts=ts, score=float(np.clip(score, -1, 1)), direction=direction,
            confidence=float(min(conf, 1.0)), agreement=float(agree),
            stop_atr=float(stop_atr), target_atr=float(target_atr), horizon_bars=max(1, horizon),
            regime=regime, contributions=tuple(sorted(contribs, key=lambda c: -abs(c.strength))),
            blocked=bool(vetoes), block_reasons=tuple(vetoes),
        )

"""Contrato común de los agentes de señal.

Cada agente es un especialista que **sólo opina**: devuelve dirección, confianza,
horizonte, stop/target sugeridos y una explicación legible. Nunca dimensiona ni
envía órdenes; eso es responsabilidad de la policy y del motor de riesgo.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from propfut.data.features import FeatureFrame
from propfut.data.news import NewsState
from propfut.regime.detector import Regime, RegimeState


@dataclass(frozen=True, slots=True)
class AgentSignal:
    agent: str
    root: str
    ts: datetime
    direction: float  # [-1, 1]; 0 = sin opinión
    confidence: float  # [0, 1]
    horizon_bars: int
    stop_atr: float | None = None
    target_atr: float | None = None
    explanation: str = ""
    veto: bool = False  # aviso de bloqueo (p.ej. noticias); el RiskEngine decide igualmente
    tags: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not -1.0 <= self.direction <= 1.0:
            raise ValueError(f"{self.agent}: direction fuera de [-1,1]: {self.direction}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.agent}: confidence fuera de [0,1]: {self.confidence}")

    @property
    def strength(self) -> float:
        return self.direction * self.confidence

    @property
    def is_neutral(self) -> bool:
        return self.direction == 0 or self.confidence == 0


@dataclass
class MarketContext:
    """Todo lo que un agente puede ver en el instante ``ts`` (nada posterior)."""

    root: str
    ts: datetime
    i: int
    frame: FeatureFrame
    row: Mapping[str, float]
    regime: RegimeState
    news: NewsState
    peers: Mapping[str, tuple[FeatureFrame, int]] = field(default_factory=dict)

    def f(self, key: str) -> float:
        return float(self.row.get(key, math.nan))

    def hist(self, col: str, n: int) -> np.ndarray:
        return self.frame.window(col, self.i, n)

    def peer_hist(self, root: str, col: str, n: int) -> np.ndarray | None:
        if root not in self.peers:
            return None
        frame, j = self.peers[root]
        if j < 0:
            return None
        return frame.window(col, j, n)


def finite(*xs: float) -> bool:
    return all(x is not None and math.isfinite(x) for x in xs)


def clip01(x: float) -> float:
    return 0.0 if not math.isfinite(x) else max(0.0, min(1.0, x))


class Agent(ABC):
    """Clase base. ``regime_affinity`` indica en qué regímenes es fiable el agente (0-1)."""

    name: str = "agent"
    default_affinity: Mapping[Regime, float] = {}

    def __init__(self, params: Mapping[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})
        aff = self.params.pop("regime_affinity", None)
        self.regime_affinity: dict[Regime, float] = dict(self.default_affinity)
        if aff:
            self.regime_affinity.update({Regime(k): float(v) for k, v in aff.items()})

    def p(self, key: str, default: Any) -> Any:
        return self.params.get(key, default)

    def neutral(self, ctx: MarketContext, why: str = "sin setup") -> AgentSignal:
        return AgentSignal(self.name, ctx.root, ctx.ts, 0.0, 0.0, 1, explanation=why)

    def signal(
        self,
        ctx: MarketContext,
        direction: float,
        confidence: float,
        horizon: int,
        stop_atr: float | None,
        target_atr: float | None,
        explanation: str,
        **tags: float,
    ) -> AgentSignal:
        return AgentSignal(
            self.name, ctx.root, ctx.ts,
            float(max(-1.0, min(1.0, direction))), clip01(confidence), int(horizon),
            stop_atr, target_atr, explanation, tags=tags,
        )

    def affinity(self, regime: RegimeState) -> float:
        """Afinidad esperada dada la distribución de probabilidad del régimen."""
        if not regime.probs:
            return 0.0
        return sum(p * self.regime_affinity.get(r, 0.5) for r, p in regime.probs.items())

    @abstractmethod
    def generate(self, ctx: MarketContext) -> AgentSignal: ...

    def __call__(self, ctx: MarketContext) -> AgentSignal:
        try:
            return self.generate(ctx)
        except Exception as exc:  # un agente defectuoso nunca debe tumbar el sistema
            return self.neutral(ctx, f"error en agente: {exc!r}")

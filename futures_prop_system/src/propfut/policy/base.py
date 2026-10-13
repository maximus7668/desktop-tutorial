"""Policy layer: decide SI se opera, con qué fracción del presupuesto de riesgo y cómo entrar.

La policy NUNCA dimensiona en contratos ni puede saltarse límites: produce una
``size_fraction`` en [0, 1] que el RiskEngine multiplica por el presupuesto que
él mismo calcula. Una policy RL defectuosa sólo puede, como mucho, operar menos.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from propfut.agents.ensemble import EnsembleDecision
from propfut.core.config import EnsembleConfig, PolicyConfig
from propfut.core.types import OrderType
from propfut.regime.detector import Regime

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicyContext:
    dd_utilization: float
    daily_pnl_norm: float  # daily_pnl / daily_loss_soft_stop
    trades_today: int
    consecutive_losses: int
    minutes_to_flatten: float


@dataclass(frozen=True)
class PolicyAction:
    take: bool
    size_fraction: float
    entry_type: OrderType
    stop_atr: float
    target_atr: float
    reason: str


class Policy(Protocol):
    def decide(self, decision: EnsembleDecision, ctx: PolicyContext) -> PolicyAction: ...


SIZE_LEVELS = (0.0, 0.33, 0.66, 1.0)
REGIME_ORDER = (Regime.TREND_UP, Regime.TREND_DOWN, Regime.RANGE, Regime.HIGH_VOL, Regime.SQUEEZE,
                Regime.NEWS_DRIVEN)


def build_observation(decision: EnsembleDecision, ctx: PolicyContext) -> np.ndarray:
    """Vector de observación común a la policy RL y a su entorno de entrenamiento."""
    r = decision.regime
    obs = [
        decision.score, decision.confidence, decision.agreement,
        min(decision.stop_atr, 5.0) / 5.0, min(decision.target_atr / max(decision.stop_atr, 1e-6), 5.0) / 5.0,
        *[r.p(x) for x in REGIME_ORDER], r.risk_multiplier,
        ctx.dd_utilization, float(np.clip(ctx.daily_pnl_norm, -1.5, 1.5)),
        min(ctx.trades_today, 10) / 10.0, min(ctx.consecutive_losses, 5) / 5.0,
        float(np.clip(ctx.minutes_to_flatten / 400.0, -1.0, 1.0)),
    ]
    return np.asarray(obs, dtype=np.float32)


OBS_DIM = 5 + len(REGIME_ORDER) + 1 + 5


class HeuristicPolicy:
    """Policy por defecto, transparente y conservadora."""

    def __init__(self, cfg: PolicyConfig | None = None, ens: EnsembleConfig | None = None,
                 default_entry: str = "market") -> None:
        self.cfg = cfg or PolicyConfig()
        self.ens = ens or EnsembleConfig()
        self.default_entry = default_entry

    def decide(self, decision: EnsembleDecision, ctx: PolicyContext) -> PolicyAction:
        stop, tgt = decision.stop_atr, decision.target_atr
        if not decision.actionable:
            why = "; ".join(decision.block_reasons) if decision.blocked else "sin consenso suficiente"
            return PolicyAction(False, 0.0, OrderType.MARKET, stop, tgt, why)
        min_c = self.ens.min_confidence
        conviction = float(np.clip((decision.confidence - min_c) / max(1e-6, 1 - min_c), 0, 1))
        size = self.cfg.min_size_fraction + (1 - self.cfg.min_size_fraction) * math.sqrt(conviction)
        size *= decision.regime.risk_multiplier
        size *= 0.75 + 0.25 * float(np.clip((decision.agreement - 0.6) / 0.4, 0, 1))
        if ctx.consecutive_losses >= 1:
            size *= 0.75
        if ctx.daily_pnl_norm < -0.5:
            size *= 0.5
        if size < 0.5 * self.cfg.min_size_fraction:
            return PolicyAction(False, 0.0, OrderType.MARKET, stop, tgt,
                                f"tamaño residual {size:.2f} (régimen {decision.regime.label.value})")
        lbl = decision.regime.label
        entry = OrderType.LIMIT if (self.default_entry == "limit" or lbl is Regime.RANGE) else OrderType.MARKET
        tgt = max(tgt, 1.5 * stop)
        return PolicyAction(True, float(min(size, 1.0)), entry, stop, tgt,
                            f"conv={conviction:.2f} régimen={lbl.value} size={size:.2f}")


class RLSizingPolicy:
    """Envuelve un modelo entrenado (stable-baselines3) que elige el nivel de tamaño.

    Si el modelo no está disponible o falla, cae a la :class:`HeuristicPolicy`.
    La acción RL sólo puede **reducir** el tamaño propuesto por la heurística
    (salvaguarda: el agente RL no puede aumentar la exposición más allá de una
    policy transparente y auditada).
    """

    def __init__(self, cfg: PolicyConfig, fallback: HeuristicPolicy) -> None:
        self.cfg = cfg
        self.fallback = fallback
        self.model = None
        if cfg.model_path:
            try:
                from stable_baselines3 import PPO  # type: ignore[import-not-found]

                self.model = PPO.load(cfg.model_path)
            except Exception as exc:  # pragma: no cover - depende de dependencias opcionales
                log.warning("No se pudo cargar el modelo RL (%s); usando heurística", exc)

    def decide(self, decision: EnsembleDecision, ctx: PolicyContext) -> PolicyAction:
        base = self.fallback.decide(decision, ctx)
        if not base.take or self.model is None:
            return base
        try:
            action, _ = self.model.predict(build_observation(decision, ctx), deterministic=True)
            level = SIZE_LEVELS[int(action)]
        except Exception as exc:  # pragma: no cover
            log.warning("Fallo de inferencia RL (%s); usando heurística", exc)
            return base
        size = min(base.size_fraction, level)
        if size <= 0:
            return PolicyAction(False, 0.0, base.entry_type, base.stop_atr, base.target_atr, "RL: no operar")
        return PolicyAction(True, size, base.entry_type, base.stop_atr, base.target_atr,
                            f"RL nivel={level:.2f} | {base.reason}")


def make_policy(cfg: PolicyConfig, ens: EnsembleConfig, default_entry: str = "market") -> Policy:
    h = HeuristicPolicy(cfg, ens, default_entry)
    return RLSizingPolicy(cfg, h) if cfg.kind == "rl" else h

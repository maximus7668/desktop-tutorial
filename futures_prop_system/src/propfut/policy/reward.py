"""Función de recompensa orientada a supervivencia en cuenta de fondeo.

Penaliza fuertemente: romper reglas (DD trailing / diario), aumentos de
utilización del drawdown, sobreoperación y riesgo excesivo cuando el colchón es
pequeño. Premia: PnL ajustado por riesgo, consistencia y profit factor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardConfig:
    risk_unit_usd: float = 250.0
    breach_penalty: float = 50.0
    daily_stop_penalty: float = 3.0
    dd_increase_penalty: float = 8.0  # por unidad de utilización ganada
    overtrade_penalty: float = 0.5  # por trade sobre el objetivo diario
    target_trades_per_day: int = 3
    risk_when_stressed_penalty: float = 1.0  # size x dd_util
    consistency_bonus: float = 5.0
    profit_factor_bonus: float = 3.0
    target_bonus: float = 20.0


@dataclass(frozen=True)
class StepInfo:
    pnl_usd: float
    size_fraction: float
    dd_util_before: float
    dd_util_after: float
    trades_today: int
    daily_stop_hit: bool
    breached: bool


def step_reward(cfg: RewardConfig, s: StepInfo) -> float:
    r = s.pnl_usd / cfg.risk_unit_usd
    r -= cfg.dd_increase_penalty * max(0.0, s.dd_util_after - s.dd_util_before)
    r -= cfg.overtrade_penalty * max(0, s.trades_today - cfg.target_trades_per_day)
    r -= cfg.risk_when_stressed_penalty * s.size_fraction * s.dd_util_before
    if s.daily_stop_hit:
        r -= cfg.daily_stop_penalty
    if s.breached:
        r -= cfg.breach_penalty
    return float(r)


def episode_bonus(
    cfg: RewardConfig, daily_pnls: list[float], gross_win: float, gross_loss: float, target_reached: bool
) -> float:
    total = sum(daily_pnls)
    bonus = 0.0
    if total > 0 and daily_pnls:
        best_share = max(daily_pnls) / total
        bonus += cfg.consistency_bonus * max(0.0, 1.0 - best_share)
    if gross_loss > 0:
        bonus += cfg.profit_factor_bonus * min(gross_win / gross_loss, 3.0) / 3.0
    if target_reached:
        bonus += cfg.target_bonus
    return bonus

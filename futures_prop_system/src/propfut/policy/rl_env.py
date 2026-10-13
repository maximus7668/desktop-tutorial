"""Entorno RL (API Gymnasium) para aprender *sizing y selección* bajo reglas de prop firm.

Diseño deliberadamente acotado: el agente RL no genera señales ni gestiona
órdenes; recibe oportunidades ya filtradas por el ensemble (con su resultado
en múltiplos de R, costes incluidos, obtenido en backtest walk-forward) y decide
el nivel de tamaño ``{0, 0.33, 0.66, 1}``. Así el espacio de búsqueda es
pequeño, la señal de recompensa es densa y el riesgo de sobreajuste se reduce.

Entrena SIEMPRE con oportunidades out-of-sample (generadas por walk-forward) y
valida en un periodo posterior nunca visto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from propfut.core.config import PropFirmRules, TrailingMode
from propfut.policy.base import OBS_DIM, SIZE_LEVELS
from propfut.policy.reward import RewardConfig, StepInfo, episode_bonus, step_reward

try:  # gymnasium es opcional
    import gymnasium as gym  # type: ignore[import-not-found]
    from gymnasium import spaces  # type: ignore[import-not-found]

    _Base: Any = gym.Env
except Exception:  # pragma: no cover
    gym = None
    spaces = None
    _Base = object


@dataclass(frozen=True)
class Opportunities:
    obs: np.ndarray  # (N, OBS_DIM) sin las 5 últimas columnas de contexto de cuenta
    r_multiple: np.ndarray  # (N,) resultado neto por unidad de riesgo a tamaño completo
    day: np.ndarray  # (N,) índice de día de trading (no decreciente)

    def __post_init__(self) -> None:
        if not (len(self.obs) == len(self.r_multiple) == len(self.day)):
            raise ValueError("Longitudes inconsistentes")
        if np.any(np.diff(self.day) < 0):
            raise ValueError("Las oportunidades deben estar en orden temporal")


class PropFirmSizingEnv(_Base):  # type: ignore[misc]
    metadata: dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        opps: Opportunities,
        rules: PropFirmRules,
        risk_per_trade_usd: float = 250.0,
        daily_soft_stop_usd: float = 600.0,
        episode_days: int = 20,
        reward: RewardConfig | None = None,
        seed: int | None = None,
    ) -> None:
        self.opps = opps
        self.rules = rules
        self.risk_usd = risk_per_trade_usd
        self.soft_stop = daily_soft_stop_usd
        self.episode_days = episode_days
        self.rcfg = reward or RewardConfig(risk_unit_usd=risk_per_trade_usd)
        self.rng = np.random.default_rng(seed)
        if spaces is not None:
            self.action_space = spaces.Discrete(len(SIZE_LEVELS))
            self.observation_space = spaces.Box(-5.0, 5.0, shape=(OBS_DIM,), dtype=np.float32)
        self._days = np.unique(opps.day)
        # estado de episodio (se reinicia en reset)
        self.i = self.end = 0
        self.cur_day = 0
        self.equity = self.hwm = rules.account_size
        self.threshold = rules.initial_threshold
        self.daily_pnl = 0.0
        self.trades_today = self.consec_losses = 0
        self.day_stopped = False
        self.day_pnls: list[float] = []
        self.gross_win = self.gross_loss = 0.0

    # ------------------------------------------------------------------ #
    def _ctx(self) -> np.ndarray:
        return np.array([
            self.dd_util,
            np.clip(self.daily_pnl / self.soft_stop, -1.5, 1.5),
            min(self.trades_today, 10) / 10.0,
            min(self.consec_losses, 5) / 5.0,
            0.5,
        ], dtype=np.float32)

    def _obs(self) -> np.ndarray:
        if self.i >= self.end:
            return np.zeros(OBS_DIM, dtype=np.float32)
        base = self.opps.obs[self.i][: OBS_DIM - 5]
        return np.concatenate([base, self._ctx()]).astype(np.float32)

    @property
    def dd_util(self) -> float:
        return float(np.clip(1 - (self.equity - self.threshold) / self.rules.max_loss, 0, 1))

    def _new_day(self) -> None:
        if self.rules.trailing_mode is TrailingMode.END_OF_DAY:
            self.hwm = max(self.hwm, self.equity)
            self._raise()
        self.day_pnls.append(self.daily_pnl)
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consec_losses = 0
        self.day_stopped = False

    def _raise(self) -> None:
        new = self.hwm - self.rules.max_loss
        if self.rules.trailing_lock_level is not None:
            new = min(new, self.rules.trailing_lock_level)
        self.threshold = max(self.threshold, new)

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        n_days = len(self._days)
        span = min(self.episode_days, n_days)
        d0 = int(self.rng.integers(0, max(1, n_days - span + 1)))
        days = self._days[d0 : d0 + span]
        idx = np.where(np.isin(self.opps.day, days))[0]
        self.i, self.end = int(idx[0]), int(idx[-1]) + 1
        self.cur_day = self.opps.day[self.i]
        self.equity = self.rules.account_size
        self.hwm = self.equity
        self.threshold = self.rules.initial_threshold
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consec_losses = 0
        self.day_stopped = False
        self.day_pnls = []
        self.gross_win = self.gross_loss = 0.0
        return self._obs(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        size = SIZE_LEVELS[int(action)]
        if self.day_stopped:
            size = 0.0  # el motor de riesgo real tampoco permitiría operar
        before = self.dd_util
        pnl = size * self.risk_usd * float(self.opps.r_multiple[self.i])
        if size > 0:
            self.trades_today += 1
            if pnl > 0:
                self.gross_win += pnl
                self.consec_losses = 0
            else:
                self.gross_loss += -pnl
                self.consec_losses += 1
        self.equity += pnl
        self.daily_pnl += pnl
        if self.rules.trailing_mode is TrailingMode.INTRADAY and self.equity > self.hwm:
            self.hwm = self.equity
            self._raise()
        breached = self.equity <= self.threshold
        dll = self.rules.daily_loss_limit
        if dll is not None and self.daily_pnl <= -dll and self.rules.daily_loss_mode == "breach":
            breached = True
        stop_hit = self.daily_pnl <= -self.soft_stop and not self.day_stopped
        if stop_hit:
            self.day_stopped = True
        r = step_reward(self.rcfg, StepInfo(pnl, size, before, self.dd_util, self.trades_today, stop_hit, breached))

        self.i += 1
        if self.i < self.end and self.opps.day[self.i] != self.cur_day:
            self.cur_day = self.opps.day[self.i]
            self._new_day()
        terminated = breached
        truncated = self.i >= self.end
        if terminated or truncated:
            self.day_pnls.append(self.daily_pnl)
            target = (not breached) and (self.equity - self.rules.account_size >= self.rules.profit_target)
            r += episode_bonus(self.rcfg, self.day_pnls, self.gross_win, self.gross_loss, target)
        info = {"equity": self.equity, "threshold": self.threshold, "breached": breached}
        return self._obs(), float(r), bool(terminated), bool(truncated), info

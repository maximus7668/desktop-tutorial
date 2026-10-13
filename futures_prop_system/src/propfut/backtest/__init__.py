"""Backtesting, métricas de prop firm, walk-forward, Monte Carlo y anti-overfitting."""

from propfut.backtest.engine import BacktestResult, run_backtest
from propfut.backtest.metrics import PropMetrics, compute_metrics
from propfut.backtest.monte_carlo import PropChallengeSimulator, days_from_history, stress_suite

__all__ = [
    "BacktestResult", "run_backtest", "PropMetrics", "compute_metrics",
    "PropChallengeSimulator", "days_from_history", "stress_suite",
]

"""Test de integración: invariantes de seguridad del sistema completo sobre datos sintéticos.

No se comprueba rentabilidad (los datos sintéticos no la garantizan), sino que el
sistema NUNCA incumple sus propias reglas ni las de la prop firm.
"""

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from propfut.backtest.engine import run_backtest
from propfut.backtest.monte_carlo import days_from_history, stress_suite

CT = ZoneInfo("America/Chicago")


@pytest.fixture(scope="module")
def result(cfg, market):
    return run_backtest(cfg, market, warmup_days=8)


def test_accounting_integrity(result, cfg):
    acc = result.system.account
    total = sum(t.net_pnl for t in result.trades)
    assert acc.balance == pytest.approx(cfg.account.account_size + total, abs=1e-6)
    assert result.metrics.n_trades == len(result.trades)


def test_never_breaches_firm_rules(result, cfg):
    assert not result.metrics.breached
    assert result.metrics.worst_day > -cfg.account.daily_loss_limit
    assert result.metrics.max_trailing_utilization < 1.0


def test_trades_respect_session_rules(result, cfg):
    for t in result.trades:
        e, x = t.entry_ts.astimezone(CT), t.exit_ts.astimezone(CT)
        assert e.date() == x.date(), "posición mantenida overnight"
        assert (x.hour, x.minute) <= (cfg.account.flatten_time.hour, cfg.account.flatten_time.minute)
        mins_open = (e.hour * 60 + e.minute) - (8 * 60 + 30)
        assert mins_open >= cfg.risk.no_entry_minutes_after_open
        assert t.qty * 0.1 <= cfg.risk.max_mini_equiv_contracts + 1e-9


def test_no_entries_day_before_roll(result):
    # MES/MNQ H25 -> M25 rola el 13-mar-2025: el 12 no se abren posiciones
    assert all(t.entry_ts.astimezone(CT).date().isoformat() != "2025-03-12" for t in result.trades)


def test_losses_bounded_by_planned_risk(result, cfg):
    for t in result.trades:
        # el peor caso permitido es el riesgo planificado (stop + buffer de slippage);
        # se tolera 1 tick extra por contrato por gaps
        tol = 1.25 * t.qty
        assert t.net_pnl >= -(t.initial_risk_usd + tol), t.to_dict()


def test_daily_limits_respected(result, cfg):
    d = result.daily
    if d.empty:
        pytest.skip("sin días operados")
    worst_intraday = (d["min_equity"] - d["start_balance"]).min()
    # el flatten interno salta a -600; con los stops ya colocados no debe acercarse al DLL de la firma
    assert worst_intraday > -cfg.account.daily_loss_limit
    assert (d["trades"] <= cfg.risk.max_trades_per_day).all()


def test_monte_carlo_and_stress_run(result, cfg):
    days = days_from_history(result.daily)
    assert days.shape[1] == 3
    table = stress_suite(result.daily, cfg.account, n_sims=200, max_days=30)
    assert len(table) >= 5
    assert ((table["P(pass)"] + table["P(bust)"] + table["P(timeout)"]).round(6) == 1).all()


def test_slippage_stress_is_worse(cfg, market, result):
    worse = run_backtest(cfg, market, warmup_days=8, slippage_multiplier=3.0)
    assert worse.metrics.net_pnl <= result.metrics.net_pnl + 1e-6 or worse.metrics.n_trades != result.metrics.n_trades


def test_all_signal_agents_participate(result):
    # el agente intermarket necesita barras de pares alineadas y SIN look-ahead
    for name in ("trend", "mean_reversion", "order_flow", "auction", "intermarket"):
        assert result.agent_stats.get(name, {}).get("n", 0) > 0, name


def test_equity_curve_shape(result):
    eq = result.equity
    assert isinstance(eq, pd.DataFrame) and {"equity", "threshold"} <= set(eq.columns)
    assert (eq["threshold"].diff().dropna() >= -1e-9).all(), "el umbral trailing nunca baja"

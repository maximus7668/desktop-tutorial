from datetime import date

import pytest

from propfut.core.config import TrailingMode
from propfut.risk.account import AccountState


def test_eod_trailing_and_lock(cfg):
    acc = AccountState(cfg.account)  # EOD, lock en 50.000
    acc.start_day(date(2025, 3, 3))
    acc.on_fill(1500.0, 0.0, opened=False)
    acc.mark(0.0, open_pnl_high=500.0)
    assert acc.threshold == 48000  # no se mueve intradía
    acc.start_day(date(2025, 3, 4))
    assert acc.threshold == 49500
    acc.on_fill(1000.0, 0.0, opened=False)
    acc.start_day(date(2025, 3, 5))
    assert acc.threshold == 50000  # bloqueado en el balance inicial


def test_intraday_trailing_uses_unrealized_peak(cfg):
    rules = cfg.account.model_copy(update={"trailing_mode": TrailingMode.INTRADAY, "trailing_lock_level": None})
    acc = AccountState(rules)
    acc.start_day(date(2025, 3, 3))
    acc.mark(100.0, open_pnl_low=-100.0, open_pnl_high=800.0)
    assert acc.hwm == 50800 and acc.threshold == 48800
    assert not acc.breached
    acc.mark(-1200.0, open_pnl_low=-1200.0)
    assert acc.breached and "MAX LOSS" in acc.breach_reason


def test_daily_loss_pause_vs_breach(cfg):
    acc = AccountState(cfg.account)  # pause
    acc.start_day(date(2025, 3, 3))
    acc.mark(-1000.0, open_pnl_low=-1000.0)
    assert acc.day_locked and not acc.breached
    acc.start_day(date(2025, 3, 4))
    assert not acc.day_locked
    strict = AccountState(cfg.account.model_copy(update={"daily_loss_mode": "breach"}))
    strict.start_day(date(2025, 3, 3))
    strict.mark(-1000.0, open_pnl_low=-1000.0)
    assert strict.breached


def test_consistency_and_target(cfg):
    acc = AccountState(cfg.account)
    for d, pnl in zip(range(3, 6), (2500.0, 300.0, 300.0), strict=True):
        acc.start_day(date(2025, 3, d))
        acc.on_fill(pnl, 0.0, opened=True)
    assert acc.total_pnl == 3100
    assert acc.best_day_share() == pytest.approx(2500 / 3100)
    assert not acc.target_reached()  # 80 % > 50 %: regla de consistencia
    acc.start_day(date(2025, 3, 6))
    acc.on_fill(2000.0, 0.0, opened=True)
    acc.start_day(date(2025, 3, 7))
    acc.on_fill(500.0, 0.0, opened=True)
    assert acc.best_day_share() <= 0.5 and acc.target_reached()


def test_intraday_peak_of_position_closed_within_bar_counts(cfg):
    rules = cfg.account.model_copy(update={"trailing_mode": TrailingMode.INTRADAY, "trailing_lock_level": None})
    acc = AccountState(rules)
    acc.start_day(date(2025, 3, 3))
    # la posición llegó a +600 dentro de la barra y salió por stop con -100
    acc.on_fill(-100.0, 0.0, opened=False)
    acc.mark(0.0, equity_high=50600.0)
    assert acc.hwm == 50600 and acc.threshold == 48600

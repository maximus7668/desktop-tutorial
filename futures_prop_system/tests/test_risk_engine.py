from datetime import datetime, timedelta, timezone

import pytest

from propfut.core.types import Side
from propfut.data.news import Impact, NewsCalendar, NewsEvent
from propfut.risk.engine import PositionRisk, RiskActionType, TradeIntent
from tests.conftest import RTH_TS

UTC = timezone.utc


def intent(root="MES", side=Side.LONG, entry=5000.0, stop=4990.0, target=5020.0, ts=RTH_TS, frac=1.0):
    return TradeIntent(root, f"{root}H25", side, entry, stop, target, ts, size_fraction=frac)


def test_sizing_exact(risk, account):
    d = risk.evaluate(intent(), account, [])
    assert d.approved, d.reasons
    # 10 pts * $5 + (2 buffer + 1 slippage) ticks * 1.25 + 2 * 0.62 comisión = 54.99 $/contrato
    assert d.risk_per_contract == pytest.approx(54.99)
    assert d.qty == 3  # presupuesto = min(200, 0.12*1750, 0.40*600) = 200 -> floor(200/54.99)
    assert d.checks["worst_case_loss"] == pytest.approx(3 * 54.99, abs=0.01)


def test_size_fraction_scales(risk, account):
    assert risk.evaluate(intent(frac=0.5), account, []).qty == 1


def test_veto_when_breached(risk, account):
    account.breached, account.breach_reason = True, "test"
    d = risk.evaluate(intent(), account, [])
    assert not d.approved and "rota" in d.reasons[0]


@pytest.mark.parametrize(
    "ts,needle",
    [
        (datetime(2025, 3, 4, 3, 0, tzinfo=UTC), "RTH"),                 # 21:00 CT
        (datetime(2025, 3, 4, 14, 35, tzinfo=UTC), "apertura"),          # 08:35 CT
        (datetime(2025, 3, 4, 20, 55, tzinfo=UTC), "cierre obligatorio"),  # 14:55 CT
    ],
)
def test_time_vetoes(risk, account, ts, needle):
    d = risk.evaluate(intent(ts=ts), account, [])
    assert not d.approved and needle in d.reasons[0], d.reasons


def test_news_blackout(risk, account):
    risk.news = NewsCalendar([NewsEvent(RTH_TS + timedelta(minutes=5), "CPI", Impact.HIGH)])
    d = risk.evaluate(intent(), account, [])
    assert not d.approved and "noticias" in d.reasons[0]


def test_daily_limits(risk, account, cfg):
    account.balance -= cfg.risk.daily_loss_soft_stop_usd
    assert "Soft stop" in risk.evaluate(intent(), account, []).reasons[0]
    account.balance += cfg.risk.daily_loss_soft_stop_usd
    account.trades_today = cfg.risk.max_trades_per_day
    assert "Máximo de operaciones" in risk.evaluate(intent(), account, []).reasons[0]
    account.trades_today = 0
    account.balance += 1000  # supera el profit lock diario
    assert "Profit lock" in risk.evaluate(intent(), account, []).reasons[0]


def test_cooldown_after_loss(risk, account):
    account.on_trade_closed(-50.0, RTH_TS - timedelta(minutes=5))
    assert "Cooldown" in risk.evaluate(intent(), account, []).reasons[0]


@pytest.mark.parametrize(
    "kw,needle",
    [({"stop": 5010.0}, "lado incorrecto"), ({"stop": 4999.75}, "demasiado cercano"),
     ({"target": 5005.0}, "R:R")],
)
def test_stop_validation(risk, account, kw, needle):
    d = risk.evaluate(intent(**kw), account, [])
    assert not d.approved and needle in d.reasons[0], d.reasons


def test_no_pyramiding_and_no_stopless_positions(risk, account):
    pos = PositionRisk("MES", "MESH25", 1, 5000.0, 4990.0, 5000.0)
    assert "sin piramidación" in risk.evaluate(intent(), account, [pos]).reasons[0]
    naked = PositionRisk("MNQ", "MNQH25", 1, 18000.0, None, 18000.0)
    assert "sin stop" in risk.evaluate(intent(), account, [naked]).reasons[0]


def test_correlation_reduces_size(risk, account):
    mnq = PositionRisk("MNQ", "MNQH25", 10, 18000.0, 17990.0, 18000.0)
    d = risk.evaluate(intent(), account, [mnq])
    assert d.approved and d.qty == 1
    assert any("correlacionado" in r for r in d.reasons)
    # dirección opuesta = cobertura parcial -> no se reduce por correlación
    d2 = risk.evaluate(intent(side=Side.SHORT, stop=5010.0, target=4980.0), account, [mnq])
    assert d2.approved and d2.qty == 2


def test_drawdown_tiers_reduce_risk(risk, account):
    account.balance -= 1100  # 55 % del drawdown usado
    account.day_start_balance = account.equity  # aislamos el efecto del tier (pérdida de días previos)
    d = risk.evaluate(intent(stop=4995.0), account, [])
    assert d.checks["dd_multiplier"] == 0.5
    # presupuesto = min(200, 0.12*(900-250), 240) * 0.5 = 39 -> 1 contrato de 29.99
    assert d.approved and d.qty == 1
    assert not risk.evaluate(intent(), account, []).approved  # stop de 10 pts ya no cabe


def test_contract_limit(risk, account):
    es = PositionRisk("ES", "ESH25", 3, 5000.0, 4999.0, 5000.0)
    d = risk.evaluate(intent(), account, [es])
    assert not d.approved and "Límite de contratos" in d.reasons[0]


def test_circuit_breakers(risk, account, cfg):
    pos = [PositionRisk("MES", "MESH25", 1, 5000.0, 4990.0, 5000.0)]
    flat_ts = datetime(2025, 3, 4, 21, 8, tzinfo=UTC)  # 15:08 CT
    kinds = {a.kind for a in risk.check_circuit_breakers(account, pos, flat_ts)}
    assert RiskActionType.FLATTEN_ALL in kinds
    account.balance -= cfg.risk.daily_loss_flatten_usd
    acts = risk.check_circuit_breakers(account, pos, RTH_TS)
    assert any(a.kind is RiskActionType.FLATTEN_ALL for a in acts)
    assert risk.is_halted(account.trade_date)
    assert "Día detenido" in risk.evaluate(intent(), account, []).reasons[0]


def test_kill_switch(risk, account):
    risk.engage_kill_switch("manual")
    assert not risk.evaluate(intent(), account, []).approved
    acts = risk.check_circuit_breakers(account, [], RTH_TS)
    assert acts[-1].kind is RiskActionType.HALT_ACCOUNT


def test_roll_guard_blocks_entries(risk, account):
    risk.roll_guard = lambda root, td: False
    d = risk.evaluate(intent(), account, [])
    assert not d.approved and "rollover" in d.reasons[0]

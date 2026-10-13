from datetime import timedelta

import pytest

from propfut.core.types import Bar, OrderStatus, OrderType, RunMode, Side
from propfut.execution.broker import SimulatedBroker
from propfut.execution.manager import ExecutionManager, Proposal
from propfut.execution.orders import Order
from propfut.risk.engine import TradeIntent
from tests.conftest import RTH_TS


def bar(o, h, lo, c, v=10000.0, ts=RTH_TS):
    return Bar(ts, "MES", "MESH25", o, h, lo, c, v)


@pytest.fixture()
def broker(specs):
    return SimulatedBroker({"MES": specs["MES"], "MNQ": specs["MNQ"], "ES": specs["ES"]})


def test_market_fill_with_adverse_slippage(broker):
    o = broker.submit(Order("MES", "MESH25", Side.LONG, 1, OrderType.MARKET, "entry", RTH_TS))
    f = broker.process_bar(bar(5000, 5005, 4995, 5002))
    assert f[0].price == 5000.25 and o.status is OrderStatus.FILLED


def test_limit_requires_trade_through(broker):
    broker.submit(Order("MES", "MESH25", Side.LONG, 1, OrderType.LIMIT, "entry", RTH_TS, limit_price=4995.0))
    assert broker.process_bar(bar(5000, 5005, 4995, 5002)) == []  # sólo toca
    f = broker.process_bar(bar(5000, 5005, 4994.75, 5002))
    assert f[0].price == 4995.0


def test_partial_fill_by_participation(broker):
    o = broker.submit(Order("MES", "MESH25", Side.LONG, 10, OrderType.LIMIT, "entry", RTH_TS, limit_price=4995))
    f = broker.process_bar(bar(5000, 5005, 4990, 5002, v=100))
    assert f[0].qty == 5 and o.status is OrderStatus.PARTIALLY_FILLED


def test_stop_gap_fills_at_open_plus_slippage(broker):
    broker.submit(Order("MES", "MESH25", Side.SHORT, 1, OrderType.STOP, "stop", RTH_TS, stop_price=4990.0))
    f = broker.process_exits(bar(4985, 4986, 4980, 4982))
    assert f[0].price == 4984.75


def _intent(entry=5000.0, stop=4990.0, target=5020.0, side=Side.LONG):
    return TradeIntent("MES", "MESH25", side, entry, stop, target, RTH_TS)


def _manager(risk, specs, cfg, mode=RunMode.BACKTEST):
    br = SimulatedBroker({"MES": specs["MES"], "MNQ": specs["MNQ"], "ES": specs["ES"]})
    return ExecutionManager(br, br.specs, risk, cfg.execution, cfg.policy, mode)


def test_bracket_stop_wins_same_bar_and_accounting(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg)
    d = risk.evaluate(_intent(), account, [])
    orders = em.submit_decision(d, RTH_TS)
    assert [o.tag for o in orders] == ["entry", "stop", "target"]
    assert orders[1].status is OrderStatus.HELD
    b = bar(5000, 5030, 4985, 5010, ts=RTH_TS + timedelta(minutes=5))
    em.on_fills(em.broker.process_bar(b), account)
    em.on_fills(em.broker.process_exits(b), account)  # target activado en la barra no puede llenarse
    assert em.position("MES") is None
    t = em.trades[-1]
    assert t.exit_reason == "stop" and t.qty == d.qty
    assert account.balance == pytest.approx(50000 + t.net_pnl)
    assert t.net_pnl >= -d.risk_usd - 1e-9  # el stop + buffer cubre el slippage asumido
    assert all(o.status.is_terminal for o in em.broker.orders.values())


def test_target_fill_cancels_stop_and_breakeven(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg)
    em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    b1 = bar(5000, 5004, 4998, 5003, ts=RTH_TS + timedelta(minutes=5))
    em.on_fills(em.broker.process_bar(b1) + em.broker.process_exits(b1), account)
    pos = em.position("MES")
    assert pos is not None
    em.on_bar_end("MES", 5012.0, 5013.0, 5003.0, 4.0, b1.ts)  # +1.2R -> breakeven
    assert pos.stop_price > pos.avg_price
    b2 = bar(5012, 5025, 5011, 5024, ts=RTH_TS + timedelta(minutes=10))
    em.on_fills(em.broker.process_bar(b2) + em.broker.process_exits(b2), account)
    assert em.position("MES") is None and em.trades[-1].exit_reason == "target"
    assert not em.broker.open_orders("MES")


def test_flatten_cancels_and_closes(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg)
    em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    b1 = bar(5000, 5004, 4998, 5003, ts=RTH_TS + timedelta(minutes=5))
    em.on_fills(em.broker.process_bar(b1) + em.broker.process_exits(b1), account)
    em.flatten(None, "test", b1.ts)
    assert [o.tag for o in em.broker.open_orders("MES")] == ["flatten"]
    b2 = bar(5003, 5004, 5001, 5002, ts=RTH_TS + timedelta(minutes=10))
    em.on_fills(em.broker.process_bar(b2) + em.broker.process_exits(b2), account)
    assert em.position("MES") is None and em.trades[-1].exit_reason == "test"


def test_proposal_mode_revalidates_on_confirm(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg, RunMode.LIVE_PROPOSAL)
    prop = em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    assert isinstance(prop, Proposal) and em.working_entry_qty()["MES"] > 0
    assert not em.broker.open_orders()
    # expirada
    assert em.confirm(prop.id, RTH_TS + timedelta(hours=1), account, {}) is None
    prop2 = em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    account.balance -= 1000  # el estado cambia antes de confirmar -> veto
    assert em.confirm(prop2.id, RTH_TS + timedelta(seconds=30), account, {}) is None
    account.balance += 1000
    prop3 = em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    assert em.confirm(prop3.id, RTH_TS + timedelta(seconds=30), account, {})


def test_analysis_mode_never_sends(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg, RunMode.ANALYSIS)
    assert em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS) is None
    assert not em.broker.orders


def test_roll_position_keeps_stop(risk, account, specs, cfg):
    em = _manager(risk, specs, cfg)
    em.submit_decision(risk.evaluate(_intent(), account, []), RTH_TS)
    b1 = bar(5000, 5004, 4998, 5003, ts=RTH_TS + timedelta(minutes=5))
    em.on_fills(em.broker.process_bar(b1) + em.broker.process_exits(b1), account)
    qty = em.position("MES").qty
    em.roll_position("MES", "MESM25", 0.0, b1.ts, policy="roll")
    b2 = Bar(RTH_TS + timedelta(minutes=10), "MES", "MESM25", 5003, 5004, 5001, 5002, 10000)
    em.on_fills(em.broker.process_bar(b2), account)
    em.on_fills(em.broker.process_exits(b2), account)
    pos = em.position("MES")
    assert pos is not None and pos.contract == "MESM25" and pos.qty == qty
    stops = [o for o in em.broker.open_orders("MES") if o.tag == "stop"]
    assert len(stops) == 1 and stops[0].remaining == qty

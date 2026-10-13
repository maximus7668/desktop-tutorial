from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from propfut.contracts.calendar import ContractCalendar
from propfut.contracts.rollover import (
    RollEvent,
    RolloverManager,
    build_continuous,
    determine_roll_schedule,
)
from propfut.contracts.specs import ContractId, ContractSpec
from propfut.core.config import ContractSpecConfig, RollMethod

HOLIDAYS = [date(2025, 11, 27), date(2025, 12, 25), date(2026, 1, 1)]


def test_tick_value_must_match(cfg):
    raw = cfg.spec("ES").model_dump()
    raw["tick_value"] = 10.0
    with pytest.raises(ValidationError):
        ContractSpecConfig.model_validate(raw)


def test_price_math(specs):
    es = specs["ES"]
    assert es.pnl(5000.0, 5001.0, 1) == 50.0
    assert es.pnl(5000.0, 4999.75, -2) == 25.0
    assert es.round_price(5000.13) == 5000.25
    assert es.round_stop(4990.10, is_long=True) == 4990.0
    assert es.round_stop(5010.10, is_long=False) == 5010.25
    assert specs["MES"].mini_equivalent(10) == pytest.approx(1.0)
    six_j = specs["6J"]
    assert six_j.ticks_to_usd(1) == pytest.approx(6.25)
    assert six_j.is_tick_aligned(six_j.round_price(0.0068123))


@pytest.mark.parametrize(
    "symbol,roots,expected",
    [("ESZ25", None, ("ES", 2025, 12)), ("6EZ25", {"6E"}, ("6E", 2025, 12)),
     ("MESH2026", None, ("MES", 2026, 3)), ("GCZ5", None, ("GC", 2025, 12))],
)
def test_parse(symbol, roots, expected):
    c = ContractId.parse(symbol, roots, ref_year=2025)
    assert (c.root, c.year, c.month) == expected


@pytest.mark.parametrize(
    "root,year,month,last_trade",
    [
        ("ES", 2025, 12, date(2025, 12, 19)),
        ("6E", 2025, 12, date(2025, 12, 15)),
        ("CL", 2025, 12, date(2025, 11, 20)),
        ("CL", 2026, 1, date(2025, 12, 19)),  # el 25-dic es festivo
        ("GC", 2025, 12, date(2025, 12, 29)),
        ("NG", 2025, 12, date(2025, 11, 25)),  # Thanksgiving
    ],
)
def test_last_trade_dates(specs, root, year, month, last_trade):
    cal = ContractCalendar(specs[root], HOLIDAYS)
    assert cal.last_trade_date(ContractId(year, month, root)) == last_trade


def test_first_notice_and_roll(specs):
    gc = ContractCalendar(specs["GC"], HOLIDAYS)
    d = gc.dates(ContractId(2025, 12, "GC"))
    assert d.first_notice == date(2025, 11, 28)
    assert d.roll_date == date(2025, 11, 24)  # 3 días hábiles antes del FND (27-nov festivo)
    es = ContractCalendar(specs["ES"], HOLIDAYS)
    assert es.dates(ContractId(2025, 12, "ES")).roll_date == date(2025, 12, 11)
    assert es.front_contract(date(2025, 12, 10)).symbol == "ESZ25"
    assert es.front_contract(date(2025, 12, 11)).symbol == "ESH26"
    assert es.next_contract(ContractId(2025, 12, "ES")).symbol == "ESH26"


def _contract_df(start: str, n: int, price: float, vol: list[float] | None = None) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    p = price + pd.Series(range(n), dtype=float).to_numpy()
    df = pd.DataFrame({"open": p, "high": p + 1, "low": p - 1, "close": p,
                       "volume": vol if vol is not None else [100.0] * n}, index=idx)
    df["trade_date"] = idx.tz_localize(None).normalize()
    return df


def test_continuous_difference_adjustment():
    old = _contract_df("2025-01-01", 10, 100.0)
    new = _contract_df("2025-01-01", 10, 110.0)  # contango constante de 10
    sched = [RollEvent(date(2025, 1, 6), "ESH25", "ESM25", "calendar")]
    cont = build_continuous({"ESH25": old, "ESM25": new}, sched, "difference")
    assert list(cont["contract"].iloc[[0, -1]]) == ["ESH25", "ESM25"]
    assert cont["roll"].sum() == 1
    # sin gap artificial: las diferencias de cierre son siempre +1
    assert (cont["close"].diff().dropna() == 1.0).all()
    # precios reales intactos
    assert cont.loc[cont["contract"] == "ESH25", "raw_close"].iloc[0] == 100.0
    ratio = build_continuous({"ESH25": old, "ESM25": new}, sched, "ratio")
    assert ratio["close"].iloc[-1] == new["close"].iloc[-1]


def test_volume_roll_never_after_calendar(specs):
    cal = ContractCalendar(specs["ES"])
    cfg_roll = specs["ES"].cfg.roll
    assert cfg_roll.method is RollMethod.VOLUME
    n = 60
    old = _contract_df("2025-02-01", n, 100.0, [1000.0 - 15 * i for i in range(n)])
    new = _contract_df("2025-02-01", n, 110.0, [10.0 + 15 * i for i in range(n)])
    sched = determine_roll_schedule({"ESH25": old, "ESM25": new}, cal)
    safety = cal.dates(ContractId(2025, 3, "ES")).roll_date
    assert len(sched) == 1 and sched[0].roll_date <= safety
    # sin cruce de volumen -> se usa la fecha de calendario
    flat = determine_roll_schedule(
        {"ESH25": _contract_df("2025-02-01", n, 100.0, [1000.0] * n),
         "ESM25": _contract_df("2025-02-01", n, 110.0, [1.0] * n)}, cal)
    assert flat[0].roll_date == safety


def test_rollover_manager(specs):
    rm = RolloverManager(ContractCalendar(specs["ES"]))
    assert rm.active_contract(date(2025, 12, 10)) == "ESZ25"
    assert rm.needs_roll("ESZ25", date(2025, 12, 11))
    assert not rm.entries_allowed(date(2025, 12, 10))  # 1 día hábil antes del roll
    st = rm.status(date(2025, 12, 1))
    assert st["active"] == "ESZ25" and st["business_days_to_roll"] == 8


def test_spec_wrapper_margin(specs):
    assert isinstance(specs["MES"], ContractSpec)
    assert specs["MES"].margin(3) == 150.0

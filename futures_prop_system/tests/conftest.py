from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from propfut.contracts.specs import ContractSpec
from propfut.core.config import SystemConfig, load_config
from propfut.core.sessions import SessionCalendar
from propfut.data.providers import SyntheticConfig, SyntheticFuturesGenerator, prepare_market_data
from propfut.risk.account import AccountState
from propfut.risk.engine import RiskEngine

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


@pytest.fixture(scope="session")
def cfg() -> SystemConfig:
    return load_config(ROOT / "config" / "account_50k.yaml")


@pytest.fixture(scope="session")
def specs(cfg: SystemConfig) -> dict[str, ContractSpec]:
    return {r: ContractSpec(s) for r, s in cfg.contract_library.items()}


def session_for(cfg: SystemConfig, root: str) -> SessionCalendar:
    s = cfg.spec(root).session
    return SessionCalendar(s.timezone, cfg.account.day_reset_time, s.rth_open, s.rth_close)


@pytest.fixture()
def risk(cfg: SystemConfig, specs: dict[str, ContractSpec]) -> RiskEngine:
    roots = ("MES", "MNQ", "ES")
    return RiskEngine(cfg.account, cfg.risk, {r: specs[r] for r in roots},
                      {r: session_for(cfg, r) for r in roots})


@pytest.fixture()
def account(cfg: SystemConfig, risk: RiskEngine) -> AccountState:
    acc = AccountState(cfg.account)
    acc.start_day(risk.account_cal.trade_date(RTH_TS))
    return acc


# martes 4-mar-2025 10:00 CT (CST = UTC-6)
RTH_TS = datetime(2025, 3, 4, 16, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def raw_bars(cfg: SystemConfig, specs: dict[str, ContractSpec]) -> dict[str, dict[str, pd.DataFrame]]:
    gen = SyntheticFuturesGenerator(SyntheticConfig(business_days=55, seed=11))
    return gen.generate({r: specs[r] for r in cfg.instruments})


@pytest.fixture(scope="session")
def market(cfg: SystemConfig, specs: dict[str, ContractSpec], raw_bars) -> dict[str, pd.DataFrame]:
    return {
        r: prepare_market_data(specs[r], raw_bars[r], session_for(cfg, r)).continuous
        for r in cfg.instruments
    }

"""Utilidades compartidas por los scripts (carga de config y datos)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from propfut.contracts.specs import ContractSpec  # noqa: E402
from propfut.core.config import SystemConfig, load_config  # noqa: E402
from propfut.core.sessions import SessionCalendar  # noqa: E402
from propfut.data.news import Impact, NewsCalendar, NewsEvent  # noqa: E402
from propfut.data.providers import (  # noqa: E402
    FileDataProvider,
    SyntheticConfig,
    SyntheticFuturesGenerator,
    prepare_market_data,
)


def load(config: str) -> SystemConfig:
    return load_config(config)


def session_for(cfg: SystemConfig, root: str) -> SessionCalendar:
    s = cfg.spec(root).session
    return SessionCalendar(s.timezone, cfg.account.day_reset_time, s.rth_open, s.rth_close)


def build_market(
    cfg: SystemConfig, data_dir: str | None, days: int, seed: int, start: date | None = None
) -> tuple[dict[str, pd.DataFrame], NewsCalendar]:
    """Datos reales desde ``data_dir`` (ver FileDataProvider) o sintéticos si es ``None``."""
    specs = {r: ContractSpec(cfg.spec(r)) for r in cfg.instruments}
    news = NewsCalendar()
    if data_dir:
        prov = FileDataProvider(data_dir)
        s = start or date(2000, 1, 1)
        raw = {r: prov.contract_bars(r, s, s + timedelta(days=int(days * 1.5))) for r in cfg.instruments}
        news_csv = Path(data_dir) / "news.csv"
        if news_csv.exists():
            news = NewsCalendar.from_csv(news_csv)
    else:
        gen = SyntheticFuturesGenerator(SyntheticConfig(business_days=days, seed=seed))
        raw = gen.generate(specs)
        news = NewsCalendar([NewsEvent(ts, title, Impact.HIGH) for ts, title in gen.news_events()])
    market = {
        r: prepare_market_data(specs[r], raw[r], session_for(cfg, r)).continuous for r in cfg.instruments
    }
    return market, news

import math

import numpy as np
import pandas as pd
import pytest

from propfut.agents.base import AgentSignal, MarketContext
from propfut.agents.ensemble import DynamicEnsemble, PerformanceTracker
from propfut.agents.macro import MacroNewsAgent
from propfut.agents.technical import MeanReversionAgent, TrendMomentumAgent
from propfut.core.config import EnsembleConfig
from propfut.data.features import FeatureFrame
from propfut.data.news import NewsState
from propfut.regime.detector import Regime, RegimeDetector
from propfut.regime.hmm import GaussianHMM
from tests.conftest import RTH_TS

BASE = {"er": 0.5, "ema_spread_atr": 1.5, "ema_slope_atr": 0.2, "atr_rank": 0.5,
        "bb_width_rank": 0.5, "squeeze_ratio": 1.2}


def test_regimes():
    det = RegimeDetector()
    assert det.classify("A", BASE).label is Regime.TREND_UP
    down = {**BASE, "ema_spread_atr": -1.5, "ema_slope_atr": -0.2}
    assert det.classify("B", down).label is Regime.TREND_DOWN
    rng = {**BASE, "er": 0.1, "ema_spread_atr": 0.1}
    assert det.classify("C", rng).label is Regime.RANGE
    hv = {**rng, "atr_rank": 0.98}
    st = det.classify("D", hv)
    assert st.label is Regime.HIGH_VOL and st.risk_multiplier < 0.6
    sq = {**rng, "bb_width_rank": 0.02, "squeeze_ratio": 0.7}
    assert det.classify("E", sq).label is Regime.SQUEEZE
    news = det.classify("F", BASE, NewsState(in_blackout=True))
    assert news.label is Regime.NEWS_DRIVEN and news.risk_multiplier == 0.0
    assert det.classify("G", {**BASE, "er": math.nan}).label is Regime.UNKNOWN


def test_hysteresis():
    det = RegimeDetector()
    rng = {**BASE, "er": 0.1, "ema_spread_atr": 0.1}
    weak_trend = {**BASE, "er": 0.36, "ema_spread_atr": 0.8, "ema_slope_atr": 0.1}
    det.classify("X", rng)
    labels = [det.classify("X", weak_trend).label for _ in range(3)]
    assert labels == [Regime.RANGE, Regime.RANGE, Regime.TREND_UP]


def test_hmm_separates_volatility_states():
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 0.3, 400), rng.normal(2.0, 0.3, 400)])
    hmm = GaussianHMM(2).fit(x)
    p = hmm.filter(x)
    assert p[:400, 1].mean() < 0.1 and p[400:, 1].mean() > 0.9


def _ctx(rows: list[dict], regime=None, news=None) -> MarketContext:
    idx = pd.date_range("2025-03-04 15:00", periods=len(rows), freq="5min", tz="UTC")
    df = pd.DataFrame(rows, index=idx)
    df["contract"], df["trade_date"] = "MESH25", idx.tz_localize(None).normalize()
    ff = FeatureFrame.from_frame("MES", df)
    reg = regime or RegimeDetector().classify("Z", BASE)
    return MarketContext("MES", RTH_TS, len(rows) - 1, ff, ff.row(len(rows) - 1), reg, news or NewsState())


def test_trend_agent_breakout_and_warmup():
    row = {"close": 5010.0, "atr": 4.0, "donchian_high": 5005.0, "donchian_low": 4980.0, "er": 0.55,
           "ema_spread_atr": 1.2, "ema_slope_atr": 0.2, "ema_fast": 5003.0, "volume_rel_tod": 2.0}
    s = TrendMomentumAgent()(_ctx([row] * 3))
    assert s.direction == 1.0 and s.confidence > 0.5 and "Breakout" in s.explanation
    s2 = TrendMomentumAgent()(_ctx([{**row, "atr": math.nan}] * 3))
    assert s2.is_neutral


def test_mean_reversion_only_in_non_directional():
    rows = [{"bb_z": 2.6, "vwap_dist_atr": 2.0, "er": 0.15, "atr": 4.0},
            {"bb_z": 2.2, "vwap_dist_atr": 1.8, "er": 0.15, "atr": 4.0}]
    s = MeanReversionAgent()(_ctx(rows))
    assert s.direction == -1.0
    rows_trend = [{**r, "er": 0.6} for r in rows]
    assert MeanReversionAgent()(_ctx(rows_trend)).is_neutral


def test_macro_agent_vetoes_and_ensemble_blocks():
    ctx = _ctx([{"close": 1.0}], news=NewsState(minutes_to_next=5.0))
    veto = MacroNewsAgent()(ctx)
    assert veto.veto
    agents = [TrendMomentumAgent(), MacroNewsAgent()]
    ens = DynamicEnsemble(agents)
    strong = AgentSignal("trend", "MES", RTH_TS, 1.0, 0.9, 10, 1.5, 3.0, "x")
    dec = ens.combine("MES", RTH_TS, [strong, veto], ctx.regime)
    assert dec.blocked and not dec.actionable


def test_ensemble_agreement_and_threshold():
    agents = [TrendMomentumAgent(), MeanReversionAgent()]
    ens = DynamicEnsemble(agents)
    reg = RegimeDetector().classify("Q", BASE)
    a = AgentSignal("trend", "MES", RTH_TS, 1.0, 0.8, 10, 1.5, 3.0, "a")
    b = AgentSignal("mean_reversion", "MES", RTH_TS, -1.0, 0.8, 8, 1.2, 2.0, "b")
    dec = ens.combine("MES", RTH_TS, [a, b], reg)
    # en tendencia la afinidad por régimen hace dominar al agente de tendencia
    assert dec.score > 0 and 0.6 < dec.agreement < 0.9 and dec.direction == 1
    # en rango manda mean-reversion con las mismas señales
    rng_reg = RegimeDetector().classify("R", {**BASE, "er": 0.1, "ema_spread_atr": 0.1})
    assert ens.combine("MES", RTH_TS, [a, b], rng_reg).direction == -1
    # exigiendo más acuerdo, el conflicto impide operar
    strict = DynamicEnsemble(agents, EnsembleConfig(min_agreement=0.9))
    assert strict.combine("MES", RTH_TS, [a, b], reg).direction == 0
    dec2 = ens.combine("MES", RTH_TS, [a], reg)
    assert dec2.direction == 1 and dec2.stop_atr == pytest.approx(1.5)


def test_performance_tracker_no_lookahead():
    tr = PerformanceTracker(halflife=5, min_samples=5)
    sig = AgentSignal("trend", "MES", RTH_TS, 1.0, 1.0, 3, explanation="")
    for k in range(10):
        tr.record("MES", sig, k * 10, 100.0, 1.0)
        tr.resolve("MES", k * 10 + 2, 200.0)  # todavía no vence: no debe contar
        assert tr.factor("trend") == 1.0 or k > 0
        tr.resolve("MES", k * 10 + 3, 101.0)
    assert tr.factor("trend") > 1.5


def test_agent_exception_is_contained():
    class Broken(TrendMomentumAgent):
        def generate(self, ctx):
            raise RuntimeError("boom")
    s = Broken()(_ctx([{"close": 1.0}]))
    assert s.is_neutral and "boom" in s.explanation


def test_signal_validation():
    with pytest.raises(ValueError):
        AgentSignal("x", "MES", RTH_TS, 2.0, 0.5, 1)

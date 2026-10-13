import numpy as np
import pandas as pd

from propfut.contracts.specs import ContractSpec
from propfut.data.features import FeatureEngine
from propfut.data.volume_profile import compute_profile
from tests.conftest import session_for


def test_features_are_causal(cfg, specs, market):
    """Recalcular con datos truncados debe dar EXACTAMENTE lo mismo en el pasado (sin look-ahead)."""
    full = market["MES"]
    base_cols = [c for c in full.columns if c in ("open", "high", "low", "close", "volume", "bid_volume",
                                                   "ask_volume", "open_interest", "contract", "roll", "adj")
                 or c.startswith("raw_")]
    raw = full[base_cols]
    eng = FeatureEngine(ContractSpec(cfg.spec("MES")), session_for(cfg, "MES"))
    a = eng.compute(raw)
    cut = int(len(raw) * 0.6)
    b = eng.compute(raw.iloc[:cut])
    num = a.select_dtypes(include=[np.number, bool]).columns
    left = a[num].iloc[:cut].to_numpy(float)
    right = b[num].to_numpy(float)
    bad = ~np.isclose(left, right, equal_nan=True, rtol=1e-9, atol=1e-9)
    assert not bad.any(), f"columnas con look-ahead: {sorted(set(num[np.where(bad)[1]]))}"


def test_session_levels_and_roll(market):
    df = market["MES"]
    rth = df[df["is_rth"]]
    assert rth["prev_vah"].dropna().gt(rth["prev_val"].dropna()).all()
    assert (df["contract"] != df["contract"].shift()).sum() >= 2  # hubo roll
    # el retorno en la barra de roll no contiene el gap de contango
    assert df.loc[df["roll"], "ret"].abs().max() < 0.01
    # el opening range sólo existe cuando se ha completado (>= 30 min tras la apertura)
    orh = df.loc[df["or_high"].notna(), "mins_since_rth_open"]
    assert orh.min() >= 25


def test_volume_profile_value_area():
    highs = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    lows = highs - 1.0  # barras contiguas
    vols = np.array([10.0, 50.0, 100.0, 50.0, 10.0])
    p = compute_profile(highs, lows, vols, tick_size=0.25, bin_ticks=4)  # bins de 1 punto
    assert 101.0 <= p.poc <= 102.0
    assert p.val <= p.poc <= p.vah and p.vah - p.val <= 3.0 + 1e-9
    assert p.val > 99.0 and p.vah < 105.0  # las colas de poco volumen quedan fuera
    assert compute_profile(highs, lows, np.zeros(5), 0.25) is None


def test_trade_date_rolls_at_reset(cfg):
    from propfut.data.features import compute_trade_dates
    idx = pd.DatetimeIndex(["2025-03-07 22:55", "2025-03-09 23:05", "2025-03-10 14:00"], tz="UTC")
    # vie 16:55 CT -> viernes; dom 18:05 CDT -> lunes; lun 09:00 CT -> lunes
    td = compute_trade_dates(idx, session_for(cfg, "MES")).astype(str).tolist()
    assert td == ["2025-03-07", "2025-03-10", "2025-03-10"]

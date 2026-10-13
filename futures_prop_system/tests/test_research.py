from datetime import date, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from propfut.backtest.monte_carlo import PropChallengeSimulator, trade_sequence_drawdowns
from propfut.backtest.overfitting import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    min_track_record_length,
    pbo_cscv,
    probabilistic_sharpe_ratio,
)
from propfut.backtest.walk_forward import WalkForwardOptimizer, override, walk_forward_splits
from propfut.core.config import TrailingMode
from propfut.policy.base import OBS_DIM
from propfut.policy.rl_env import Opportunities, PropFirmSizingEnv


def test_mc_extremes(cfg):
    sim = PropChallengeSimulator(cfg.account)
    good = np.tile([400.0, -50.0, 450.0], (30, 1))
    r = sim.simulate(good, n_sims=200)
    assert r.p_pass == 1.0 and r.median_days_to_pass == 8  # consistencia: necesita 3000 con mejor día <= 50 %
    bad = np.tile([-300.0, -350.0, 0.0], (30, 1))
    assert sim.simulate(bad, n_sims=200).p_bust == 1.0


def test_mc_intraday_trailing_is_stricter(cfg):
    days = np.tile([0.0, -1300.0, 900.0], (5, 1))  # sube 900 y devuelve todo cada día
    eod = PropChallengeSimulator(cfg.account).run_one(days)
    intra = PropChallengeSimulator(cfg.account.model_copy(
        update={"trailing_mode": TrailingMode.INTRADAY, "trailing_lock_level": None,
                "daily_loss_limit": None})).run_one(days)
    assert eod[0] != "bust" and intra[0] == "bust"


def test_trade_shuffle_drawdowns():
    dd = trade_sequence_drawdowns([100, -50, 100, -50, -50, 100], n_sims=100)
    assert dd.min() >= 50 and dd.max() <= 150


def test_sharpe_statistics():
    assert probabilistic_sharpe_ratio(0.0, 100) == pytest.approx(0.5)
    assert expected_max_sharpe(100, 0.01) > expected_max_sharpe(10, 0.01) > 0
    rng = np.random.default_rng(1)
    r = rng.normal(0.05, 1.0, 500)
    psr = probabilistic_sharpe_ratio(0.05, 500)
    assert deflated_sharpe_ratio(r, n_trials=50, var_trials_sr=0.01) < psr
    assert min_track_record_length(rng.normal(0.2, 1, 500)) < min_track_record_length(rng.normal(0.05, 1, 500))


def test_pbo():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, (400, 10))
    assert 0.2 < pbo_cscv(noise, n_splits=10)["pbo"] < 0.8
    edge = noise.copy()
    edge[:, 0] += 0.5
    assert pbo_cscv(edge, n_splits=10)["pbo"] < 0.1


def test_walk_forward_splits_and_override(cfg):
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(100)]
    sp = walk_forward_splits(days, train_days=40, test_days=20, embargo_days=2)
    assert len(sp) == 2
    assert all(s.test_start > s.train_end for s in sp)
    assert (sp[0].test_start - sp[0].train_end).days == 3
    c2 = override(cfg, {"ensemble.min_confidence": 0.4})
    assert c2.ensemble.min_confidence == 0.4 and cfg.ensemble.min_confidence != 0.4
    with pytest.raises(ValidationError):
        override(cfg, {"risk.daily_loss_flatten_usd": 5000})  # incoherente con la firma: se rechaza


def test_robust_choice_prefers_plateau(cfg):
    wf = WalkForwardOptimizer(cfg, {}, {"a": [1, 2, 3, 4, 5]})
    scores = {(0,): 0.1, (1,): 0.9, (2,): 0.85, (3,): 0.8, (4,): 2.0}
    # (4,) es un pico aislado junto a 0.8; (2,) está en la meseta
    assert wf._robust_choice({**scores, (3,): -1.0}) in {(1,), (2,)}


def test_rl_env_runs_and_terminates_on_breach(cfg):
    n = 60
    obs = np.zeros((n, OBS_DIM - 5), dtype=np.float32)
    opps = Opportunities(obs, np.full(n, -1.0), np.repeat(np.arange(20), 3))
    env = PropFirmSizingEnv(opps, cfg.account, risk_per_trade_usd=400, daily_soft_stop_usd=10_000,
                            episode_days=20, seed=0)
    o, _ = env.reset(seed=0)
    assert o.shape == (OBS_DIM,)
    done, total, steps = False, 0.0, 0
    while not done:
        o, r, term, trunc, info = env.step(3)
        total += r
        steps += 1
        done = term or trunc
    assert info["breached"] and steps <= 6 and total < -40
    # no operar nunca rompe
    env.reset(seed=0)
    for _ in range(n):
        *_, term, trunc, info = env.step(0)
        if term or trunc:
            break
    assert not info["breached"]

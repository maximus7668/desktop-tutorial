"""Walk-forward con rejilla pequeña + PBO (CSCV) + Deflated Sharpe Ratio + Monte Carlo OOS.

Uso:
    python scripts/run_walk_forward.py --days 160 --train-days 40 --test-days 20
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from common import ROOT, build_market, load

from propfut.backtest.engine import run_backtest
from propfut.backtest.monte_carlo import PropChallengeSimulator, days_from_history
from propfut.backtest.overfitting import deflated_sharpe_ratio, pbo_cscv
from propfut.backtest.walk_forward import WalkForwardOptimizer, override, walk_forward_splits
from propfut.monitoring.logger import setup_logging

#: Rejilla deliberadamente PEQUEÑA: cada combinación extra aumenta el sesgo de selección.
GRID = {
    "ensemble.min_confidence": [0.25, 0.35],
    "policy.trail_after_r": [1.5, 2.0],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "account_50k.yaml"))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--days", type=int, default=160)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--train-days", type=int, default=40)
    ap.add_argument("--test-days", type=int, default=20)
    ap.add_argument("--warmup-days", type=int, default=10)
    args = ap.parse_args()
    setup_logging(logging.INFO)

    cfg = load(args.config)
    market, news = build_market(cfg, args.data_dir, args.days, args.seed)
    root = cfg.instruments[0]
    tdays = sorted(pd.to_datetime(market[root]["trade_date"]).dt.date.unique())[args.warmup_days:]
    splits = walk_forward_splits(tdays, args.train_days, args.test_days, embargo_days=1)
    print(f"{len(splits)} ventanas walk-forward; {np.prod([len(v) for v in GRID.values()])} combinaciones")

    wf = WalkForwardOptimizer(cfg, market, GRID, news=news, warmup_days=args.warmup_days)
    res = wf.run(splits)
    print("\nResultados OUT-OF-SAMPLE por ventana:")
    print(res.summary().to_string(index=False))

    # PBO: todas las combinaciones sobre el periodo completo, PnL diario por combinación
    daily_cols = {}
    for combo in wf.combos:
        p = wf._params(combo)
        r = run_backtest(override(cfg, p), market, news, warmup_days=args.warmup_days)
        daily_cols[str(p)] = r.daily.set_index("trade_date")["pnl"]
    mat = pd.DataFrame(daily_cols).fillna(0.0)
    if len(mat) >= 32:
        print("\nPBO (CSCV):", pbo_cscv(mat.to_numpy(), n_splits=8))
        srs = (mat.mean() / mat.std(ddof=1).replace(0, np.nan)).fillna(0.0)
        best = mat[srs.idxmax()].to_numpy()
        print(f"Deflated Sharpe Ratio de la mejor combinación: "
              f"{deflated_sharpe_ratio(best, n_trials=res.n_trials, var_trials_sr=float(srs.var(ddof=1))):.3f}")
    if len(res.oos_daily) >= 10:
        mc = PropChallengeSimulator(cfg.account).simulate(days_from_history(res.oos_daily), n_sims=3000)
        print("\nMonte Carlo sobre días OOS:", mc.to_dict())
    print("\nRegla de decisión: pasar a paper SÓLO si OOS agregado > 0, ninguna ventana rompe la cuenta,"
          " PBO < 0.3, DSR > 0.9 y P(bust) Monte Carlo < 10 %.")


if __name__ == "__main__":
    main()

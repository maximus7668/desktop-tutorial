"""Backtest completo + Monte Carlo de la evaluación + stress tests + estadísticos anti-overfitting.

Uso:
    python scripts/run_backtest.py --config config/account_50k.yaml            # datos sintéticos
    python scripts/run_backtest.py --data-dir data/ --days 250                 # datos reales
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from common import ROOT, build_market, load

from propfut.backtest.engine import run_backtest
from propfut.backtest.monte_carlo import PropChallengeSimulator, days_from_history, stress_suite
from propfut.backtest.overfitting import min_track_record_length, probabilistic_sharpe_ratio
from propfut.monitoring.dashboard import render_text
from propfut.monitoring.logger import setup_logging


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "account_50k.yaml"))
    ap.add_argument("--data-dir", default=None, help="Directorio con {ROOT}/{SYMBOL}.csv; vacío = sintético")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--warmup-days", type=int, default=15)
    ap.add_argument("--out", default=str(ROOT / "reports"))
    ap.add_argument("--decision-log", action="store_true")
    args = ap.parse_args()
    setup_logging(logging.WARNING)

    cfg = load(args.config)
    market, news = build_market(cfg, args.data_dir, args.days, args.seed)
    res = run_backtest(cfg, market, news=news, warmup_days=args.warmup_days,
                       log_dir=args.out + "/logs" if args.decision_log else None)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res.trades_frame().to_csv(out / "trades.csv", index=False)
    res.daily.to_csv(out / "daily.csv", index=False)
    res.equity.to_csv(out / "equity.csv")

    lines = [res.summary(), ""]
    if len(res.daily) >= 10:
        days = days_from_history(res.daily)
        mc = PropChallengeSimulator(cfg.account).simulate(days, n_sims=3000, max_days=60)
        lines += ["Monte Carlo de la evaluación (bootstrap por bloques de días, 60 días máx.):"]
        lines += [f"  {k}: {v}" for k, v in mc.to_dict().items()]
        lines += ["", "Stress tests:", stress_suite(res.daily, cfg.account, n_sims=1500).to_string(index=False)]
        r = res.daily["pnl"].to_numpy() / cfg.account.account_size
        sr = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else 0.0
        lines += ["", f"PSR (P[Sharpe>0]) diario: {probabilistic_sharpe_ratio(sr, len(r)):.3f}",
                  f"Min track record length (días): {min_track_record_length(r):.0f}"]
    else:
        lines.append("(menos de 10 días operados: Monte Carlo omitido)")
    lines += ["", "Agentes:"] + [f"  {k}: {v}" for k, v in res.agent_stats.items()]
    lines += ["", render_text(res.system.state(res.equity.index[-1]))] if not res.equity.empty else []
    report = "\n".join(lines)
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nFicheros en {out}/ (trades.csv, daily.csv, equity.csv, report.txt)")
    if args.data_dir is None:
        print("\n⚠️  Datos SINTÉTICOS: estos resultados sólo validan la mecánica, NO la rentabilidad.")


if __name__ == "__main__":
    main()

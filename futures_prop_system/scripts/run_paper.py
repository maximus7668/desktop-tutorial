"""Paper trading / modo propuesta sobre un replay de barras (sintéticas o de fichero).

En producción sustituye el bucle de replay por tu feed de barras cerradas y
llama a ``runner.on_bar(...)`` con cada barra.

Uso:
    python scripts/run_paper.py --mode paper
    python scripts/run_paper.py --mode live_proposal --auto-confirm   # demo: confirma todo
"""

from __future__ import annotations

import argparse
import logging

from common import ROOT, build_market, load

from propfut.backtest.walk_forward import override
from propfut.core.types import RunMode
from propfut.live import LiveRunner
from propfut.monitoring.logger import setup_logging


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "account_50k.yaml"))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--mode", default="paper", choices=["paper", "analysis", "live_proposal"])
    ap.add_argument("--history-days", type=int, default=25)
    ap.add_argument("--replay-days", type=int, default=2)
    ap.add_argument("--auto-confirm", action="store_true")
    args = ap.parse_args()
    setup_logging(logging.WARNING)

    cfg = override(load(args.config), {"monitoring.state_file": str(ROOT / "logs" / "state.json"),
                                       "monitoring.log_dir": str(ROOT / "logs")})
    market, news = build_market(cfg, args.data_dir, args.history_days + args.replay_days + 2, seed=21)
    cols = ["open", "high", "low", "close", "volume", "bid_volume", "ask_volume", "contract", "roll"]
    first = cfg.instruments[0]
    days = sorted(market[first]["trade_date"].unique())
    split_day = days[args.history_days]
    hist = {r: df[df["trade_date"] < split_day][[c for c in cols if c in df]] for r, df in market.items()}
    live = {r: df[df["trade_date"] >= split_day][[c for c in cols if c in df]] for r, df in market.items()}

    runner = LiveRunner(cfg, hist, mode=RunMode(args.mode), news=news, buffer_bars=7000)
    for ts in live[first].index:
        for r in cfg.instruments:
            if ts in live[r].index:
                b = live[r].loc[ts]
                runner.on_bar(r, ts.to_pydatetime(), b.to_dict(), str(b["contract"]))
        if args.mode == "live_proposal":
            for p in runner.system.state(ts.to_pydatetime())["proposals"]:
                print(f"[PROPUESTA] {p['summary']}  (caduca {p['expires']})")
                if args.auto_confirm:
                    ok = runner.confirm(p["id"], ts.to_pydatetime())
                    print("   -> confirmada" if ok else "   -> vetada al re-evaluar")
    print(runner.dashboard(ts.to_pydatetime()))
    print(f"Operaciones cerradas: {len(runner.system.exec.trades)}  | estado en logs/state.json")


if __name__ == "__main__":
    main()

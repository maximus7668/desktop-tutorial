from propfut.backtest.walk_forward import override
from propfut.core.types import RunMode
from propfut.live import LiveRunner


def _split(market, root, n_hist):
    df = market[root]
    cols = ["open", "high", "low", "close", "volume", "bid_volume", "ask_volume", "contract", "roll"]
    return df[cols].iloc[:n_hist], df[cols].iloc[n_hist:]


def test_paper_and_proposal_modes(cfg, market, tmp_path):
    c = override(cfg, {"monitoring.state_file": str(tmp_path / "state.json"),
                       "monitoring.log_dir": str(tmp_path / "logs")})
    n_hist = 276 * 22
    hist, future = {}, {}
    for r in c.instruments:
        hist[r], future[r] = _split(market, r, n_hist)
    for mode in (RunMode.PAPER, RunMode.LIVE_PROPOSAL):
        runner = LiveRunner(c, hist, mode=mode, buffer_bars=6000)
        n = 0
        for ts in future["MES"].index[:200]:
            for r in c.instruments:
                b = future[r].loc[ts]
                state = runner.on_bar(r, ts.to_pydatetime(), b.to_dict(), str(b["contract"]))
                n += 1
        assert n == 400 and (tmp_path / "state.json").exists()
        assert "account" in state and not state["account"]["breached"]
        if mode is RunMode.LIVE_PROPOSAL:
            assert not runner.system.exec.trades  # nada se ejecuta sin confirmación
        assert "Equity" in runner.dashboard(ts.to_pydatetime())

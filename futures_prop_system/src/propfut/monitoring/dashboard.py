"""Dashboard: snapshot de estado en JSON + render de terminal + app Streamlit opcional.

Ejecutar la app:  ``streamlit run -m propfut.monitoring.dashboard -- logs/state.json``
(o ``python -m streamlit run src/propfut/monitoring/dashboard.py -- logs/state.json``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from propfut.monitoring.logger import to_json


def write_state(path: str | Path, state: dict[str, Any]) -> None:
    """Escritura atómica del estado (el dashboard nunca lee un JSON a medias)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(to_json(state), encoding="utf-8")
    tmp.replace(p)


def render_text(state: dict[str, Any]) -> str:
    acc = state.get("account", {})
    risk = state.get("risk", {})
    lines = [
        "=" * 72,
        f" PROPFUT | {state.get('ts', '')} | modo {state.get('mode', '')}",
        "=" * 72,
        f" Equity {acc.get('equity', 0):>12,.2f}   Balance {acc.get('balance', 0):>12,.2f}   "
        f"PnL día {acc.get('daily_pnl', 0):>+10,.2f}",
        f" Umbral {acc.get('threshold', 0):>12,.2f}   Colchón {acc.get('trailing_room', 0):>12,.2f}   "
        f"DD usado {100 * float(acc.get('dd_utilization', 0)):>6.1f}%",
        f" Trades hoy {acc.get('trades_today', 0)}   Pérdidas seguidas {acc.get('consecutive_losses', 0)}   "
        f"Objetivo {'SÍ' if acc.get('target_reached') else 'no'}   ROTA: {'SÍ' if acc.get('breached') else 'no'}",
        f" Halt: {risk.get('halt_reason') or '-'}   Kill switch: {risk.get('kill_switch')}",
        "-" * 72,
        " Posiciones:",
    ]
    for p in state.get("positions", []):
        lines.append(f"   {p['root']:<5} {p['contract']:<8} qty={p['qty']:>+3} avg={p['avg_price']:<12} "
                     f"stop={p.get('stop_price')}")
    if not state.get("positions"):
        lines.append("   (ninguna)")
    contrib = state.get("agent_stats", {})
    if contrib:
        lines.append("-" * 72)
        lines.append(" Agentes (factor de rendimiento):")
        for k, v in contrib.items():
            lines.append(f"   {k:<16} n={int(v['n']):>4} media={v['ew_mean_atr']:+.3f}ATR factor={v['factor']:.2f}")
    lines.append("=" * 72)
    return "\n".join(lines)


def _streamlit_app(state_path: str) -> None:  # pragma: no cover - UI
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="propfut", layout="wide")
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    acc = state["account"]
    c = st.columns(5)
    c[0].metric("Equity", f"{acc['equity']:,.2f}", f"{acc['daily_pnl']:+,.2f} hoy")
    c[1].metric("Colchón trailing", f"{acc['trailing_room']:,.2f}")
    c[2].metric("DD usado", f"{100 * acc['dd_utilization']:.1f}%")
    c[3].metric("Trades hoy", acc["trades_today"])
    c[4].metric("Estado", "ROTA" if acc["breached"] else ("HALT" if state["risk"].get("halted_today") else "OK"))
    if state.get("equity_curve"):
        df = pd.DataFrame(state["equity_curve"]).set_index("ts")
        st.line_chart(df[["equity", "threshold"]])
    st.subheader("Posiciones")
    st.dataframe(pd.DataFrame(state.get("positions", [])))
    st.subheader("Contribución por agente")
    st.dataframe(pd.DataFrame(state.get("agent_stats", {})).T)
    st.subheader("Últimas decisiones")
    st.dataframe(pd.DataFrame(state.get("recent_decisions", [])))


if __name__ == "__main__":  # pragma: no cover
    _streamlit_app(sys.argv[1] if len(sys.argv) > 1 else "logs/state.json")

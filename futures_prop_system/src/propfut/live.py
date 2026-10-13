"""Runner de paper trading / análisis en vivo / ejecución controlada.

Recibe barras cerradas (de cualquier feed) por raíz, recalcula features sobre
un buffer deslizante y llama al MISMO :meth:`TradingSystem.on_timestamp` que el
backtest. Escribe el estado para el dashboard en cada barra.

Integración con un broker real: implementa :class:`LiveBrokerAdapter` y pásalo
como ``broker`` (ver docs/VALIDACION_Y_DESPLIEGUE.md antes de hacerlo).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

import pandas as pd

from propfut.contracts.specs import ContractSpec
from propfut.core.config import SystemConfig
from propfut.core.sessions import SessionCalendar
from propfut.core.types import RunMode
from propfut.data.features import FeatureEngine, FeatureFrame
from propfut.data.news import NewsCalendar, SentimentProvider
from propfut.execution.broker import SimulatedBroker
from propfut.execution.orders import Order
from propfut.monitoring.alerts import AlertManager
from propfut.monitoring.dashboard import render_text, write_state
from propfut.monitoring.logger import DecisionLogger
from propfut.system import TradingSystem

log = logging.getLogger(__name__)


class LiveBrokerAdapter(SimulatedBroker):
    """Punto de integración con un broker real (Rithmic/CQG/Tradovate/IBKR...).

    Requisitos mínimos de una implementación de producción:

    * ``submit``: enviar brackets **nativos del servidor** (OCO) para que el stop
      exista aunque este proceso muera; mapear ids internos <-> ids del broker.
    * Reconciliar posiciones y órdenes con el broker al arrancar y periódicamente;
      ante discrepancia: kill switch + alerta (nunca "adivinar").
    * Entregar fills reales al ExecutionManager (``process_bar``/``process_exits``
      deben devolver los fills recibidos desde la última llamada).
    * Heartbeat de conexión: si se pierde el feed o la sesión de órdenes,
      ``RiskEngine.report_execution_anomaly`` y cierre de posiciones al reconectar.
    """

    def submit(self, order: Order) -> Order:  # pragma: no cover - plantilla
        raise NotImplementedError("Implementa el envío al broker real")


class LiveRunner:
    def __init__(
        self,
        cfg: SystemConfig,
        history: Mapping[str, pd.DataFrame],
        mode: RunMode = RunMode.PAPER,
        news: NewsCalendar | None = None,
        sentiment: SentimentProvider | None = None,
        broker: SimulatedBroker | None = None,
        buffer_bars: int = 8000,
        holidays: Iterable[date] = (),
    ) -> None:
        if mode is RunMode.BACKTEST:
            raise ValueError("Usa run_backtest para backtesting")
        self.cfg = cfg
        self.buffer_bars = buffer_bars
        dlog = DecisionLogger(cfg.monitoring.log_dir, enabled=cfg.monitoring.decision_log)
        self.system = TradingSystem(cfg, news=news, sentiment=sentiment, broker=broker, mode=mode,
                                    decision_log=dlog, alerts=AlertManager(), holidays=tuple(holidays),
                                    stop_on_breach=True)
        self.engines = {
            r: FeatureEngine(ContractSpec(cfg.spec(r)), SessionCalendar(
                cfg.spec(r).session.timezone, cfg.account.day_reset_time,
                cfg.spec(r).session.rth_open, cfg.spec(r).session.rth_close))
            for r in cfg.instruments
        }
        base_cols = ["open", "high", "low", "close", "volume", "contract", "roll"]
        self.raw: dict[str, pd.DataFrame] = {}
        for r in cfg.instruments:
            df = history.get(r)
            if df is None or df.empty:
                raise ValueError(f"Se necesita histórico para calentar {r}")
            keep = [c for c in base_cols + ["bid_volume", "ask_volume", "open_interest"] if c in df.columns]
            self.raw[r] = df[keep].tail(buffer_bars).copy()
        frames = {r: FeatureFrame.from_frame(r, self.engines[r].compute(df)) for r, df in self.raw.items()}
        self.system.set_frames(frames)
        self.system.fit_models({r: len(f) for r, f in frames.items()})

    def on_bar(
        self,
        root: str,
        ts: datetime,
        bar: Mapping[str, Any],
        contract: str,
        roll_spread: float | None = None,
    ) -> dict[str, Any]:
        """Procesa una barra CERRADA de ``root``. Devuelve el estado actual.

        Si ``contract`` cambia (roll), ``roll_spread`` = precio_nuevo - precio_viejo
        observado en el momento del roll: el buffer se back-ajusta por diferencia
        para que las features no vean un gap artificial.
        """
        row = {k: bar[k] for k in ("open", "high", "low", "close", "volume")}
        for k in ("bid_volume", "ask_volume", "open_interest"):
            if k in bar:
                row[k] = bar[k]
        prev = self.raw[root]
        row["contract"] = contract
        row["roll"] = bool(len(prev) and prev["contract"].iloc[-1] != contract)
        if row["roll"]:
            if roll_spread is None:
                log.warning("Roll en %s sin roll_spread: las features verán un gap artificial", root)
            else:
                prev = prev.copy()
                for c in ("open", "high", "low", "close"):
                    prev[c] = prev[c] + roll_spread
        new = pd.DataFrame([row], index=pd.DatetimeIndex([pd.Timestamp(ts)]))
        df = pd.concat([prev, new]).tail(self.buffer_bars)
        self.raw[root] = df
        ff = FeatureFrame.from_frame(root, self.engines[root].compute(df))
        self.system.frames[root] = ff
        self.system.on_timestamp(ts, {root: len(ff) - 1})
        state = self.system.state(ts)
        write_state(self.cfg.monitoring.state_file, state)
        return state

    # --- modo propuesta ---------------------------------------------------
    def pending_proposals(self) -> list[dict[str, Any]]:
        return self.system.state(datetime.now().astimezone())["proposals"]

    def confirm(self, proposal_id: str, now: datetime) -> bool:
        res = self.system.exec.confirm(proposal_id, now, self.system.account, self.system.last_close)
        return res is not None

    def reject(self, proposal_id: str) -> None:
        self.system.exec.reject(proposal_id)

    def kill(self, reason: str, now: datetime) -> None:
        """Kill switch manual: cierra todo y bloquea nuevas entradas."""
        self.system.risk.engage_kill_switch(reason)
        self.system.exec.flatten(None, f"KILL SWITCH: {reason}", now)

    def dashboard(self, now: datetime) -> str:
        return render_text(self.system.state(now))

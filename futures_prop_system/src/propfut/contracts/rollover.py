"""Rollover: calendario de roll, construcción de series continuas y gestor de roll en vivo.

Notas de diseño
---------------
* **Ajuste por diferencia (Panama/back-adjust)**: preserva las diferencias en
  puntos -> el PnL en USD calculado sobre la serie ajustada es correcto. Distorsiona
  los retornos porcentuales y puede producir precios negativos en históricos largos.
* **Ajuste por ratio**: preserva retornos porcentuales; distorsiona puntos/PnL.
* El sistema guarda SIEMPRE ``raw_*`` (precio real del contrato) junto al ajustado,
  y el símbolo del contrato vigente en cada barra.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import numpy as np
import pandas as pd

from propfut.contracts.calendar import ContractCalendar
from propfut.contracts.specs import ContractId
from propfut.core.config import RollMethod

OHLC = ("open", "high", "low", "close")


@dataclass(frozen=True, slots=True)
class RollEvent:
    roll_date: date
    from_contract: str
    to_contract: str
    method: str


def _daily_metric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        raise KeyError(f"Falta la columna '{col}' para rolar por {col}")
    s = df[col]
    if "trade_date" in df.columns:
        grouped = s.groupby(df["trade_date"])
    else:
        grouped = s.groupby(pd.Index(df.index).date)
    return grouped.sum() if col == "volume" else grouped.last()


def determine_roll_schedule(
    contract_bars: Mapping[str, pd.DataFrame],
    calendar: ContractCalendar,
    method: RollMethod | None = None,
) -> list[RollEvent]:
    """Calcula las fechas de roll entre contratos consecutivos.

    * ``calendar``: ``roll_date`` de :class:`ContractCalendar`.
    * ``volume`` / ``open_interest``: primer día en que el siguiente contrato supera
      al actual durante ``confirm_days`` días consecutivos, dentro de la ventana
      ``max_days_before``; **nunca después** de la fecha de calendario (red de seguridad).
    """
    cfg = calendar.spec.cfg.roll
    method = method or cfg.method
    roots = {calendar.spec.root}
    ids = sorted(ContractId.parse(s, roots) for s in contract_bars)
    events: list[RollEvent] = []
    for cur, nxt in zip(ids, ids[1:], strict=False):
        dates_cur = calendar.dates(cur)
        safety = dates_cur.roll_date
        roll = safety
        if method is not RollMethod.CALENDAR:
            col = "volume" if method is RollMethod.VOLUME else "open_interest"
            a = _daily_metric(contract_bars[cur.symbol], col)
            b = _daily_metric(contract_bars[nxt.symbol], col)
            both = pd.concat([a.rename("cur"), b.rename("nxt")], axis=1).dropna().sort_index()
            earliest = calendar.bc.shift(dates_cur.reference, -cfg.max_days_before)
            streak = 0
            for d, row in both.iterrows():
                d = pd.Timestamp(d).date()
                if d < earliest or d >= safety:
                    streak = 0
                    continue
                streak = streak + 1 if row["nxt"] > row["cur"] else 0
                if streak >= cfg.confirm_days:
                    # se rola en la sesión siguiente a la confirmación (sin look-ahead)
                    roll = calendar.bc.shift(d, 1)
                    break
            roll = min(roll, safety)
        events.append(RollEvent(roll, cur.symbol, nxt.symbol, method.value))
    return events


def trim_schedule(schedule: list[RollEvent], first: date, last: date) -> tuple[list[RollEvent], str]:
    """Restringe el calendario de roll al rango de datos [first, last].

    Devuelve los eventos dentro del rango y el contrato activo al inicio de los datos.
    """
    if not schedule:
        raise ValueError("Calendario vacío")
    active = schedule[0].from_contract
    kept: list[RollEvent] = []
    for e in sorted(schedule, key=lambda e: e.roll_date):
        if e.roll_date <= first:
            active = e.to_contract
        elif e.roll_date <= last:
            kept.append(e)
    return kept, active


def build_continuous(
    contract_bars: Mapping[str, pd.DataFrame],
    schedule: list[RollEvent],
    adjustment: Literal["difference", "ratio", "none"] = "difference",
    trade_date_col: str = "trade_date",
) -> pd.DataFrame:
    """Construye una serie continua a partir de barras por contrato.

    Cada DataFrame debe estar indexado por timestamp (tz-aware) y tener columnas
    ``open, high, low, close, volume`` y ``trade_date`` (día de trading). La
    serie usa el contrato ``from`` hasta el día de trading anterior a ``roll_date``
    y el ``to`` desde ``roll_date`` (inclusive).

    Devuelve columnas OHLC ajustadas, ``raw_*`` sin ajustar, ``contract``,
    ``roll`` (True en la primera barra de un contrato nuevo) y ``adj``
    (offset o factor aplicado).
    """
    if not schedule:
        if len(contract_bars) != 1:
            raise ValueError("Sin calendario de roll sólo se admite un contrato")
        (sym, df), = contract_bars.items()
        out = df.copy()
        for c in OHLC:
            out[f"raw_{c}"] = out[c]
        out["contract"] = sym
        out["roll"] = False
        out["adj"] = 0.0 if adjustment != "ratio" else 1.0
        return out

    pieces: list[pd.DataFrame] = []
    first = schedule[0].from_contract
    order = [first] + [e.to_contract for e in schedule]
    bounds: list[tuple[date | None, date | None]] = []
    for i, _ in enumerate(order):
        start = schedule[i - 1].roll_date if i > 0 else None
        end = schedule[i].roll_date if i < len(schedule) else None
        bounds.append((start, end))

    for sym, (start, end) in zip(order, bounds, strict=True):
        df = contract_bars[sym]
        td = pd.to_datetime(pd.Series(df[trade_date_col].to_numpy(), index=df.index))
        mask = np.ones(len(df), dtype=bool)
        if start is not None:
            mask &= (td >= pd.Timestamp(start)).to_numpy()
        if end is not None:
            mask &= (td < pd.Timestamp(end)).to_numpy()
        piece = df.loc[mask].copy()
        piece["contract"] = sym
        pieces.append(piece)

    # gaps de roll: comparamos el cierre de ambos contratos en el último timestamp
    # común ANTERIOR al roll (el dato que existía en el momento de rolar)
    gaps: list[float] = []
    for ev, prev_piece in zip(schedule, pieces[:-1], strict=True):
        old = contract_bars[ev.from_contract]
        new = contract_bars[ev.to_contract]
        if prev_piece.empty:
            raise ValueError(f"Sin datos del contrato {ev.from_contract} antes del roll {ev.roll_date}")
        cutoff = prev_piece.index[-1]
        common = old.index.intersection(new.index)
        common = common[common <= cutoff]
        if len(common) == 0:
            raise ValueError(f"Sin timestamps comunes entre {ev.from_contract} y {ev.to_contract}")
        ts = common[-1]
        o, n = float(old.at[ts, "close"]), float(new.at[ts, "close"])
        if adjustment == "ratio":
            if o <= 0 or n <= 0:
                raise ValueError("El ajuste por ratio requiere precios positivos")
            gaps.append(n / o)
        else:
            gaps.append(n - o)

    out_pieces: list[pd.DataFrame] = []
    k = len(pieces)
    for i, piece in enumerate(pieces):
        p = piece.copy()
        for c in OHLC:
            p[f"raw_{c}"] = p[c]
        if adjustment == "difference":
            offset = float(sum(gaps[i:])) if i < k - 1 else 0.0
            for c in OHLC:
                p[c] = p[c] + offset
            p["adj"] = offset
        elif adjustment == "ratio":
            factor = float(np.prod(gaps[i:])) if i < k - 1 else 1.0
            for c in OHLC:
                p[c] = p[c] * factor
            p["adj"] = factor
        else:
            p["adj"] = 0.0
        p["roll"] = False
        if i > 0 and not p.empty:
            p.iloc[0, p.columns.get_loc("roll")] = True
        out_pieces.append(p)
    out = pd.concat(out_pieces).sort_index()
    if out.index.has_duplicates:
        raise ValueError("Timestamps duplicados en la serie continua")
    return out


class RolloverManager:
    """Gestor de roll en tiempo real: qué contrato operar y cuándo rolar posiciones."""

    def __init__(self, calendar: ContractCalendar, warn_days: int = 3) -> None:
        self.calendar = calendar
        self.warn_days = warn_days
        self._events: list[RollEvent] = []

    def set_schedule(self, events: list[RollEvent]) -> None:
        """Fija un calendario explícito (p.ej. calculado por volumen/OI)."""
        self._events = sorted(events, key=lambda e: e.roll_date)

    def active_contract(self, as_of: date) -> str:
        if self._events:
            current = self._events[0].from_contract
            for e in self._events:
                if as_of >= e.roll_date:
                    current = e.to_contract
            return current
        return self.calendar.front_contract(as_of).symbol

    def needs_roll(self, held_contract: str, as_of: date) -> bool:
        """``True`` si una posición en ``held_contract`` ya no está en el contrato activo."""
        return held_contract != self.active_contract(as_of)

    def entries_allowed(self, as_of: date) -> bool:
        """Bloquea nuevas entradas el día hábil anterior al roll (spreads anchos, liquidez migrando)."""
        if self._events:
            upcoming = [e.roll_date for e in self._events if e.roll_date > as_of]
            return not upcoming or self.calendar.bc.business_days_between(as_of, upcoming[0]) > 1
        return self.calendar.days_to_roll(as_of) > 1

    def status(self, as_of: date, now: datetime | None = None) -> dict[str, object]:
        front = self.calendar.front_contract(as_of)
        d = self.calendar.dates(front)
        days = self.calendar.bc.business_days_between(as_of, d.roll_date)
        return {
            "root": self.calendar.spec.root,
            "active": self.active_contract(as_of),
            "roll_date": d.roll_date.isoformat(),
            "last_trade": d.last_trade.isoformat(),
            "first_notice": d.first_notice.isoformat() if d.first_notice else None,
            "business_days_to_roll": days,
            "warning": days <= self.warn_days,
        }

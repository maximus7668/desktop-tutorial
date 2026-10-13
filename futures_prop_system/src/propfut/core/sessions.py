"""Gestión de sesiones (RTH / ETH) y del "trading day" de futuros.

Convención: todos los timestamps del sistema son ``datetime`` con zona horaria
(UTC recomendado). Las reglas horarias se evalúan en la zona del exchange o de
la prop firm (normalmente ``America/Chicago``).

En CME Globex la sesión que abre a las 17:00 CT pertenece al *día de trading*
del día hábil siguiente; por eso ``trade_date`` desplaza esas horas.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _ensure_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError(f"Timestamp sin zona horaria: {ts!r}. Usa datetimes tz-aware (UTC).")
    return ts


class SessionCalendar:
    """Calendario de sesión para un instrumento o para las reglas de la cuenta."""

    def __init__(
        self,
        timezone: str = "America/Chicago",
        day_reset_time: time = time(17, 0),
        rth_open: time = time(8, 30),
        rth_close: time = time(15, 0),
    ) -> None:
        self.tz = ZoneInfo(timezone)
        self.day_reset_time = day_reset_time
        self.rth_open = rth_open
        self.rth_close = rth_close

    def to_local(self, ts: datetime) -> datetime:
        return _ensure_aware(ts).astimezone(self.tz)

    def trade_date(self, ts: datetime) -> date:
        """Día de trading al que pertenece ``ts`` (reset a ``day_reset_time`` local)."""
        local = self.to_local(ts)
        d = local.date()
        if local.time() >= self.day_reset_time:
            d += timedelta(days=1)
        while d.weekday() >= 5:  # sábado/domingo -> lunes
            d += timedelta(days=1)
        return d

    def is_rth(self, ts: datetime) -> bool:
        local = self.to_local(ts)
        return local.weekday() < 5 and self.rth_open <= local.time() < self.rth_close

    def minutes_until(self, ts: datetime, t: time) -> float:
        """Minutos desde ``ts`` hasta la hora local ``t`` del mismo día local (negativo si ya pasó)."""
        local = self.to_local(ts)
        target = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        return (target - local).total_seconds() / 60.0

    def is_between(self, ts: datetime, start: time, end: time) -> bool:
        """``True`` si la hora local está en [start, end) — soporta ventanas que cruzan medianoche."""
        lt = self.to_local(ts).time()
        if start <= end:
            return start <= lt < end
        return lt >= start or lt < end

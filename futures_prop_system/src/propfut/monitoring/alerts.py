"""Alertas de riesgo con deduplicación y canales enchufables (log, consola, webhook)."""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Protocol

log = logging.getLogger("propfut.alerts")


class AlertLevel(IntEnum):
    INFO = 10
    WARNING = 20
    ERROR = 30
    CRITICAL = 40


@dataclass(frozen=True)
class Alert:
    level: AlertLevel
    message: str
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    key: str = ""


class AlertChannel(Protocol):
    def send(self, alert: Alert) -> None: ...


class LogChannel:
    def send(self, alert: Alert) -> None:
        log.log(logging.CRITICAL if alert.level >= AlertLevel.CRITICAL else logging.WARNING
                if alert.level >= AlertLevel.WARNING else logging.INFO, "%s", alert.message)


class WebhookChannel:
    """POST JSON (Slack/Discord/Telegram-bridge...). Fallos de red nunca interrumpen el trading."""

    def __init__(self, url: str, min_level: AlertLevel = AlertLevel.WARNING, timeout: float = 3.0) -> None:
        self.url = url
        self.min_level = min_level
        self.timeout = timeout

    def send(self, alert: Alert) -> None:
        if alert.level < self.min_level:
            return
        body = json.dumps({"text": f"[{alert.level.name}] {alert.message}"}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=self.timeout).close()  # noqa: S310
        except Exception as exc:  # pragma: no cover
            log.error("Webhook de alertas falló: %s", exc)


class AlertManager:
    def __init__(self, channels: list[AlertChannel] | None = None, dedupe_minutes: int = 10) -> None:
        self.channels = channels if channels is not None else [LogChannel()]
        self.dedupe = timedelta(minutes=dedupe_minutes)
        self._last: dict[str, datetime] = {}
        self.history: list[Alert] = []
        self._dd_levels_hit: set[float] = set()

    def emit(self, level: AlertLevel | str, message: str, key: str | None = None,
             ts: datetime | None = None) -> None:
        lvl = AlertLevel[level] if isinstance(level, str) else level
        ts = ts or datetime.now(timezone.utc)
        k = key or message
        last = self._last.get(k)
        if last is not None and ts - last < self.dedupe:
            return
        self._last[k] = ts
        a = Alert(lvl, message, ts, k)
        self.history.append(a)
        for ch in self.channels:
            ch.send(a)

    def check_drawdown(self, utilization: float, levels: list[float], ts: datetime) -> None:
        for lv in sorted(levels):
            if utilization >= lv and lv not in self._dd_levels_hit:
                self._dd_levels_hit.add(lv)
                lvl = AlertLevel.CRITICAL if lv >= 0.75 else AlertLevel.WARNING
                self.emit(lvl, f"Utilización del drawdown {utilization:.0%} (umbral {lv:.0%})",
                          key=f"dd{lv}", ts=ts)
            elif utilization < lv * 0.8:
                self._dd_levels_hit.discard(lv)

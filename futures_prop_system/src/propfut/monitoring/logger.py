"""Logging estructurado de cada decisión (JSONL), apto para auditoría y replay."""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


def _default(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: getattr(o, f.name) for f in dataclasses.fields(o) if f.name not in ("cfg",)}
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    if isinstance(o, dict):
        return {str(k.value if isinstance(k, Enum) else k): v for k, v in o.items()}
    return str(o)


def to_json(obj: Any) -> str:
    def norm(x: Any) -> Any:
        if isinstance(x, dict):
            return {str(k.value if isinstance(k, Enum) else k): norm(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [norm(v) for v in x]
        if dataclasses.is_dataclass(x) and not isinstance(x, type):
            return norm(_default(x))
        if isinstance(x, float) and not np.isfinite(x):
            return None
        return x
    return json.dumps(norm(obj), default=_default, ensure_ascii=False)


class DecisionLogger:
    """Escribe un evento JSON por línea: decisiones, vetos, órdenes, fills, acciones de riesgo."""

    def __init__(self, log_dir: str | Path | None, enabled: bool = True, keep_in_memory: int = 5000) -> None:
        self.enabled = enabled and log_dir is not None
        self.memory: list[dict[str, Any]] = []
        self.keep = keep_in_memory
        self._fh = None
        if self.enabled:
            path = Path(log_dir)  # type: ignore[arg-type]
            path.mkdir(parents=True, exist_ok=True)
            self.path = path / f"decisions_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
            self._fh = self.path.open("a", encoding="utf-8")

    def log(self, kind: str, ts: datetime, **payload: Any) -> None:
        rec = {"kind": kind, "ts": ts.isoformat(), **payload}
        if len(self.memory) < self.keep:
            self.memory.append(rec)
        if self._fh is not None:
            self._fh.write(to_json(rec) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def setup_logging(level: int = logging.INFO, file: str | Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if file:
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(file, encoding="utf-8"))
    logging.basicConfig(
        level=level, handlers=handlers, force=True,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )

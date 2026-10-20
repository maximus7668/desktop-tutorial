"""Redacción de secretos en logs, auditoría y textos que salen del sistema."""
from __future__ import annotations

import logging
import os
import re

from .config import SECRET_ENV_NAMES

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(sk|rk|pk)_(live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"whsec_[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?[^\s'\",]{6,}"),
]
MASK = "***REDACTADO***"


def _secret_values() -> list[str]:
    vals = []
    for name in SECRET_ENV_NAMES:
        v = os.environ.get(name, "")
        if len(v) >= 6:
            vals.append(v)
    return vals


def redact(text: str) -> str:
    if not text:
        return text
    for v in _secret_values():
        text = text.replace(v, MASK)
    for p in _PATTERNS:
        text = p.sub(MASK, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        record.msg = redact(msg)
        record.args = ()
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    for h in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in h.filters):
            h.addFilter(RedactingFilter())

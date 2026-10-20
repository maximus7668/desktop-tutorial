"""Arranque: abre la BD, aplica migraciones e inicializa datos base (sin sobrescribir nada)."""
from __future__ import annotations

import os
import sqlite3

from . import compliance, permissions, settings_store, tasks
from .agents import builder as _builder  # noqa: F401  (registra manejadores de aprobación)
from . import budget
from .actors import human
from . import validation as _validation  # noqa: F401
from .config import Settings
from .db import connect, migrate
from .integrations import registry
from .redact import install_log_redaction


def bootstrap(settings: Settings) -> sqlite3.Connection:
    install_log_redaction()
    conn = connect(settings.database_path)
    migrate(conn)
    overrides = {}
    envelope = os.environ.get("API_MONTHLY_ENVELOPE_EUR", "").strip()
    if envelope:
        overrides["api_envelope_month_cents"] = str(round(float(envelope) * 100))
    settings_store.initialize(conn, overrides)
    initial = round(settings.initial_capital_eur * 100)
    if initial > 0 and conn.execute("SELECT 1 FROM ledger WHERE kind='capital'").fetchone() is None:
        budget.add_capital(conn, human("propietario-config"), initial, "capital inicial (INITIAL_CAPITAL_EUR)")
    compliance.initialize(conn)
    permissions.seed(conn)
    tasks.seed_schedules(conn)
    registry.refresh(conn, settings)
    return conn

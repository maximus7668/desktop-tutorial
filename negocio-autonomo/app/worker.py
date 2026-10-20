"""Trabajador: ejecuta la cola de tareas y la programación. Se puede parar en cualquier momento;
al reiniciar, las tareas a medias se recuperan por caducidad del lease."""
from __future__ import annotations

import logging
import signal
import sqlite3
import time
from typing import Callable

from . import settings_store, tasks
from .actors import agent
from .agents import builder, content, director, operations, researcher, sales
from .budget import BudgetError
from .config import Settings
from .db import now_iso, transaction
from .integrations import IntegrationError, IntegrationNotConfigured
from .integrations.llm import LLMProvider
from .permissions import ActionBlocked

log = logging.getLogger("worker")

Handler = Callable[[sqlite3.Connection, Settings, LLMProvider, dict], dict]


def _h_director(conn, settings, provider, payload):
    return director.cycle(conn, agent("director"))


def _h_build(conn, settings, provider, payload):
    p = builder.build_for_experiment(conn, agent("constructor"), settings, int(payload["experiment_id"]))
    return {"product_id": p["id"], "status": p["status"]}


def _h_discover(conn, settings, provider, payload):
    return researcher.discover(conn, agent("investigador"), provider, settings, payload["topic"], payload["run_id"])


def _h_inbox(conn, settings, provider, payload):
    return researcher.import_inbox(conn, agent("investigador"))


def _h_report(conn, settings, provider, payload):
    return {"path": str(operations.report(conn, agent("operaciones"), settings))}


def _h_backup(conn, settings, provider, payload):
    return {"path": str(operations.backup(conn, agent("operaciones"), settings))}


def _h_watch(conn, settings, provider, payload):
    return operations.watch(conn, agent("operaciones"))


def _h_content(conn, settings, provider, payload):
    return content.generate(conn, agent("contenido"), settings, int(payload["product_id"]), provider)


def _h_inquiry(conn, settings, provider, payload):
    return {"status": sales.handle_inquiry(conn, agent("ventas"), int(payload["inquiry_id"]))}


HANDLERS: dict[str, Handler] = {
    "director.cycle": _h_director,
    "product.build": _h_build,
    "research.discover": _h_discover,
    "research.inbox": _h_inbox,
    "ops.report": _h_report,
    "ops.backup": _h_backup,
    "ops.watch": _h_watch,
    "sales.inquiry": _h_inquiry,
    "content.drafts": _h_content,
}

# Errores que no se arreglan reintentando: se marcan como fallidos (nunca como éxito).
NON_RETRYABLE = (IntegrationNotConfigured, BudgetError, ActionBlocked, PermissionError, KeyError, ValueError)


def _set_agent(conn: sqlite3.Connection, name: str, status: str, error: str | None = None) -> None:
    with transaction(conn):
        conn.execute("UPDATE agents SET status=?, last_run_at=?, last_error=? WHERE name=?",
                     (status, now_iso(), error, name))


def run_once(conn: sqlite3.Connection, settings: Settings, provider: LLMProvider) -> dict | None:
    if settings_store.is_on(conn, "kill_switch"):
        return None
    tasks.tick_schedules(conn)
    t = tasks.claim(conn)
    if t is None:
        return None
    handler = HANDLERS.get(t["type"])
    _set_agent(conn, t["agent"], "running")
    try:
        if handler is None:
            raise ValueError(f"tipo de tarea desconocido: {t['type']}")
        result = handler(conn, settings, provider, t["payload"])
    except NON_RETRYABLE as e:
        state = tasks.fail(conn, t["id"], f"{type(e).__name__}: {e}", retryable=False)
        _set_agent(conn, t["agent"], "error", str(e)[:300])
        return {"task": t["id"], "status": state, "error": str(e)}
    except (IntegrationError, sqlite3.OperationalError, OSError) as e:
        state = tasks.fail(conn, t["id"], f"{type(e).__name__}: {e}", retryable=True)
        _set_agent(conn, t["agent"], "error", str(e)[:300])
        return {"task": t["id"], "status": state, "error": str(e)}
    tasks.complete(conn, t["id"], result)
    _set_agent(conn, t["agent"], "idle")
    return {"task": t["id"], "status": "done", "result": result}


def run_forever(conn: sqlite3.Connection, settings: Settings, provider: LLMProvider, idle_sleep: float = 5.0) -> None:
    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("trabajador iniciado (entorno %s)", settings.app_env)
    while not stop["flag"]:
        try:
            r = run_once(conn, settings, provider)
        except Exception:  # un fallo inesperado no debe tumbar el bucle; queda en el log
            log.exception("error inesperado en el trabajador")
            r = None
        if r:
            log.info("tarea %s → %s", r["task"], r["status"])
        else:
            time.sleep(idle_sleep)
    log.info("trabajador detenido")

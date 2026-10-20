"""Permisos por agente, herramienta y acción, aplicados en el servidor.

Política efectiva = la más restrictiva entre:
  1. la fila de la tabla `permissions` (sin fila = deny),
  2. el techo del modo de operación (1, 2 o 3),
  3. el suelo financiero: las acciones con dinero nunca pasan de 'approval',
  4. la parada de emergencia: bloquea toda acción externa.
Ningún modo desactiva los controles financieros."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from . import audit, settings_store
from .actors import Actor, require_human
from .db import now_iso, rows, transaction

ORDER = {"deny": 0, "approval": 1, "allow": 2}

# (tool, action): (externa, financiera, requiere comercio activado)
CATALOG: dict[tuple[str, str], tuple[bool, bool, bool]] = {
    ("llm", "complete"): (True, False, False),
    ("web", "search"): (True, False, False),
    ("web", "fetch"): (True, False, False),
    ("research", "import"): (False, False, False),
    ("opportunity", "evaluate"): (False, False, False),
    ("experiment", "propose"): (False, False, False),
    ("product", "build"): (False, False, False),
    ("product", "publish"): (True, False, False),
    ("product", "update"): (True, False, False),
    ("analytics", "read"): (False, False, False),
    ("campaign", "prepare"): (False, False, False),
    ("ads", "spend"): (True, True, False),
    ("service", "purchase"): (True, True, False),
    ("payments", "checkout"): (True, True, True),
    ("payments", "refund"): (True, True, True),
    ("email", "send"): (True, False, False),
    ("inquiry", "reply_draft"): (False, False, False),
    ("report", "generate"): (False, False, False),
    ("content", "draft"): (False, False, False),
    ("backup", "run"): (False, False, False),
}

_RESEARCH_ONLY = {
    ("llm", "complete"), ("web", "search"), ("web", "fetch"), ("research", "import"),
    ("opportunity", "evaluate"), ("analytics", "read"), ("report", "generate"), ("backup", "run"),
    ("experiment", "propose"), ("inquiry", "reply_draft"),
}


def mode_ceiling(mode: str, tool: str, action: str) -> str:
    key = (tool, action)
    if mode == "1":
        return "allow" if key in _RESEARCH_ONLY else "deny"
    if mode == "2":
        external = CATALOG[key][0]
        return "approval" if external and key not in {("llm", "complete"), ("web", "search"), ("web", "fetch")} else "allow"
    return "allow"  # modo 3: manda la tabla de permisos (y el suelo financiero)


DEFAULT_PERMISSIONS: dict[str, list[tuple[str, str, str, int | None]]] = {
    "investigador": [("llm", "complete", "allow", 20), ("web", "search", "allow", 20),
                     ("web", "fetch", "allow", 50), ("research", "import", "allow", None)],
    "evaluador": [("opportunity", "evaluate", "allow", None), ("llm", "complete", "allow", 20)],
    "director": [("experiment", "propose", "allow", 5), ("campaign", "prepare", "allow", 5),
                 ("ads", "spend", "approval", None), ("service", "purchase", "approval", None),
                 ("report", "generate", "allow", None)],
    "constructor": [("product", "build", "allow", 10), ("product", "publish", "approval", 3),
                    ("product", "update", "approval", 10), ("llm", "complete", "allow", 20)],
    "ventas": [("inquiry", "reply_draft", "allow", 100), ("email", "send", "approval", 20),
               ("payments", "checkout", "approval", None)],
    "contenido": [("content", "draft", "allow", 10), ("llm", "complete", "allow", 10)],
    "operaciones": [("report", "generate", "allow", None), ("backup", "run", "allow", None),
                    ("analytics", "read", "allow", None), ("payments", "refund", "approval", None)],
}

AGENT_ROLES = {
    "investigador": "Descubre oportunidades y registra evidencias con fuentes",
    "evaluador": "Puntúa y compara oportunidades con criterios fijos",
    "director": "Elige hipótesis, diseña experimentos baratos y decide continuar/modificar/abandonar",
    "constructor": "Genera prototipos y páginas de prueba y los valida técnicamente",
    "ventas": "Responde consultas solo con respuestas verificadas; escala el resto",
    "operaciones": "Informes, alertas, copias de seguridad y control de presupuesto",
    "contenido": "Redacta borradores para redes con enlace medible; nunca publica",
}


@dataclass
class Decision:
    allowed: bool
    needs_approval: bool
    policy: str
    reason: str


class ActionBlocked(Exception):
    def __init__(self, decision: Decision):
        super().__init__(decision.reason)
        self.decision = decision


def seed(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        for name, role in AGENT_ROLES.items():
            conn.execute("INSERT OR IGNORE INTO agents (name, role) VALUES (?,?)", (name, role))
        for ag, perms in DEFAULT_PERMISSIONS.items():
            for tool, action, policy, limit in perms:
                conn.execute(
                    "INSERT OR IGNORE INTO permissions VALUES (?,?,?,?,?,?,?)",
                    (ag, tool, action, policy, limit, now_iso(), "system:seed"),
                )


def _uses_today(conn: sqlite3.Connection, actor: Actor, tool: str, action: str) -> int:
    day = datetime.now(timezone.utc).date().isoformat()
    r = conn.execute(
        "SELECT COUNT(*) c FROM audit_log WHERE actor=? AND action=? AND ts >= ?",
        (actor.name, f"use:{tool}.{action}", day),
    ).fetchone()
    return r["c"]


def check(conn: sqlite3.Connection, actor: Actor, tool: str, action: str) -> Decision:
    key = (tool, action)
    if key not in CATALOG:
        return Decision(False, False, "deny", f"herramienta desconocida {tool}.{action}")
    external, financial, needs_commerce = CATALOG[key]
    if external and settings_store.is_on(conn, "kill_switch"):
        return Decision(False, False, "deny", "parada de emergencia activa")
    if actor.kind == "human":
        # Las personas autenticadas actúan desde el panel; aun así los gastos pasan por el presupuesto.
        return Decision(True, False, "allow", "acción humana")
    if actor.kind != "agent":
        return Decision(False, False, "deny", "actor no autorizado")
    if needs_commerce and not settings_store.is_on(conn, "commerce_authorized"):
        return Decision(False, False, "deny", "cobros reales no autorizados por el propietario")
    row = conn.execute(
        "SELECT policy, daily_limit FROM permissions WHERE agent=? AND tool=? AND action=?",
        (actor.name, tool, action),
    ).fetchone()
    if row is None:
        return Decision(False, False, "deny", "sin permiso asignado")
    policy = row["policy"]
    ceiling = mode_ceiling(settings_store.get(conn, "mode"), tool, action)
    if ORDER[ceiling] < ORDER[policy]:
        policy = ceiling
    if financial and policy == "allow":
        policy = "approval"
    if policy == "deny":
        return Decision(False, False, policy, "denegado por política o por el modo actual")
    if row["daily_limit"] is not None and _uses_today(conn, actor, tool, action) >= row["daily_limit"]:
        return Decision(False, False, policy, "límite diario de uso alcanzado")
    if policy == "approval":
        return Decision(False, True, policy, "requiere aprobación humana")
    return Decision(True, False, policy, "permitido")


def authorize(conn: sqlite3.Connection, actor: Actor, tool: str, action: str, target: str = "") -> Decision:
    """Comprueba y registra el uso. Lanza ActionBlocked si no está permitido directamente."""
    d = check(conn, actor, tool, action)
    if d.allowed:
        audit.log(conn, actor, f"use:{tool}.{action}", target)
        return d
    audit.log(conn, actor, "blocked", f"{tool}.{action}", {"reason": d.reason, "target": target})
    raise ActionBlocked(d)


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM permissions ORDER BY agent, tool, action")


def set_permission(conn: sqlite3.Connection, actor: Actor, agent_name: str, tool: str, action: str,
                   policy: str, daily_limit: int | None = None) -> None:
    require_human(actor, "cambiar permisos")
    if actor.name == agent_name:
        raise PermissionError("nadie puede cambiar sus propios permisos")
    if (tool, action) not in CATALOG or policy not in ORDER:
        raise ValueError("permiso no válido")
    with transaction(conn):
        old = conn.execute("SELECT policy, daily_limit FROM permissions WHERE agent=? AND tool=? AND action=?",
                           (agent_name, tool, action)).fetchone()
        conn.execute(
            "INSERT INTO permissions VALUES (?,?,?,?,?,?,?) ON CONFLICT(agent, tool, action) DO UPDATE SET"
            " policy=excluded.policy, daily_limit=excluded.daily_limit, updated_at=excluded.updated_at,"
            " updated_by=excluded.updated_by",
            (agent_name, tool, action, policy, daily_limit, now_iso(), actor.label),
        )
        audit.log(conn, actor, "permission.change", f"{agent_name}:{tool}.{action}",
                  {"old": dict(old) if old else None, "new": {"policy": policy, "daily_limit": daily_limit}})

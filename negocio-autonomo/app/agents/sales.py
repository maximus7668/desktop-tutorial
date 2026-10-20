"""Agente de ventas: responde consultas SOLO con respuestas verificadas por el propietario.
Si no hay respuesta aprobada, o el mensaje parece manipulación, escala a una persona.
Las respuestas quedan como borrador; enviarlas por email requiere el permiso email.send."""
from __future__ import annotations

import re
import sqlite3

from .. import approvals, audit, permissions
from ..actors import Actor
from ..db import one, transaction
from ..untrusted import looks_like_injection

AGENT = "ventas"

# Respuestas aprobadas: (palabras clave, respuesta). Edita esta lista para añadir más.
APPROVED_ANSWERS: list[tuple[tuple[str, ...], str]] = [
    (("precio", "cuesta", "cuánto", "cuanto"),
     "El precio previsto aparece en la página e incluye IVA. Mientras el producto está en preparación no se cobra nada."),
    (("cuándo", "cuando", "disponible", "lanzamiento"),
     "Aún no hay fecha cerrada. Si dejas tu email en la página te avisaremos en cuanto esté disponible."),
    (("devolución", "devolucion", "reembolso", "desistimiento"),
     "Las condiciones de devolución y el derecho de desistimiento se detallan en el aviso legal antes de cualquier compra."),
    (("baja", "borrar", "eliminar mis datos", "privacidad"),
     "Puedes pedir la baja o el borrado de tus datos en cualquier momento escribiendo al email del aviso legal."),
]


def match_answer(message: str) -> str | None:
    m = message.lower()
    for keys, answer in APPROVED_ANSWERS:
        if any(re.search(r"\b" + re.escape(k) + r"\b", m) for k in keys):
            return answer
    return None


def handle_inquiry(conn: sqlite3.Connection, actor: Actor, inquiry_id: int) -> str:
    permissions.authorize(conn, actor, "inquiry", "reply_draft", f"inquiry:{inquiry_id}")
    inq = one(conn, "SELECT * FROM inquiries WHERE id=?", (inquiry_id,))
    if inq is None or inq["status"] != "new":
        return "skipped"
    answer = None if looks_like_injection(inq["message"]) else match_answer(inq["message"])
    with transaction(conn):
        if answer:
            conn.execute("UPDATE inquiries SET status='answered_draft', reply=? WHERE id=?", (answer, inquiry_id))
            audit.log(conn, actor, "inquiry.draft", f"inquiry:{inquiry_id}")
            return "answered_draft"
        conn.execute("UPDATE inquiries SET status='escalated' WHERE id=?", (inquiry_id,))
        approvals.request(conn, actor, "action", f"Consulta #{inquiry_id} sin respuesta verificada: revisar y responder",
                          "inquiries", inquiry_id)
        return "escalated"

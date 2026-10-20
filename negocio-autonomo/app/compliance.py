"""Lista de comprobación legal y fiscal configurable por el propietario.
El sistema NO decide si el negocio está exento de nada: bloquea publicar/cobrar hasta que una persona
confirme cada punto (idealmente tras revisión profesional)."""
from __future__ import annotations

import sqlite3

from . import audit
from .actors import Actor, require_human
from .db import now_iso, rows, transaction

ITEMS: list[tuple[str, str, str, str]] = [
    # key, título, descripción, requerido para
    ("owner_identity", "Identificación del titular (LSSI art. 10)",
     "Nombre o razón social, NIF, dirección y email de contacto visibles en el aviso legal. "
     "Variables OWNER_LEGAL_NAME, OWNER_TAX_ID, OWNER_ADDRESS, OWNER_CONTACT_EMAIL.", "publish"),
    ("privacy_policy", "Política de privacidad (RGPD / LOPDGDD)",
     "Responsable, finalidad, base jurídica (consentimiento del formulario), conservación, destinatarios "
     "(proveedor de hosting/email), derechos y reclamación ante la AEPD. Revisar el texto generado.", "publish"),
    ("commercial_comms", "Comunicaciones comerciales (LSSI art. 21)",
     "Solo se envían emails comerciales a quien lo ha consentido expresamente; baja sencilla en cada envío.", "publish"),
    ("ip_rights", "Propiedad intelectual y licencias",
     "Textos, imágenes, marcas y código usados tienen licencia compatible con uso comercial.", "publish"),
    ("tax_registration", "Alta censal (modelo 036/037) e IAE",
     "Alta en Hacienda antes de empezar a facturar. Facturar poco no exime de darse de alta.", "commerce"),
    ("social_security", "Seguridad Social / RETA",
     "Valorar con asesor la obligación de alta como autónomo según habitualidad e ingresos.", "commerce"),
    ("vat", "IVA y ventas a otros países",
     "Tipo de IVA aplicable; ventas B2C de servicios digitales a consumidores de la UE (umbral 10.000 € "
     "y régimen OSS/ventanilla única). Clientes fuera de España no implican ausencia de obligaciones.", "commerce"),
    ("invoicing", "Facturación",
     "Emisión de factura/factura simplificada por cada venta y sistema de facturación conforme a la normativa "
     "vigente (Verifactu: comprobar calendario y obligaciones con el asesor).", "commerce"),
    ("consumer_terms", "Condiciones de venta y consumidores",
     "Precio final con impuestos, información precontractual, derecho de desistimiento de 14 días y su "
     "excepción para contenido digital con consentimiento expreso, política de reembolsos, garantías.", "commerce"),
    ("payment_provider", "Proveedor de pagos verificado",
     "Cuenta de pagos a nombre del titular, verificada y en modo real; webhook configurado con secreto.", "commerce"),
    ("professional_review", "Revisión profesional",
     "Un asesor fiscal/legal ha revisado esta configuración para la situación concreta del propietario.", "commerce"),
]


def initialize(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        for key, title, desc, req in ITEMS:
            conn.execute(
                "INSERT OR IGNORE INTO compliance_items (key, title, description, required_for) VALUES (?,?,?,?)",
                (key, title, desc, req),
            )


def list_items(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM compliance_items ORDER BY required_for DESC, key")


def missing_for(conn: sqlite3.Connection, scope: str) -> list[str]:
    """Requisitos pendientes. 'commerce' incluye también los de 'publish'."""
    scopes = ("publish",) if scope == "publish" else ("publish", "commerce")
    q = "SELECT key FROM compliance_items WHERE status='pending' AND required_for IN (%s)" % ",".join("?" * len(scopes))
    return [r["key"] for r in conn.execute(q, scopes)]


def confirm(conn: sqlite3.Connection, actor: Actor, key: str, status: str, note: str = "") -> None:
    require_human(actor, "confirmar requisito legal")
    if status not in ("pending", "done", "not_applicable"):
        raise ValueError(status)
    with transaction(conn):
        cur = conn.execute(
            "UPDATE compliance_items SET status=?, confirmed_by=?, confirmed_at=?, note=? WHERE key=?",
            (status, actor.label, now_iso(), note, key),
        )
        if cur.rowcount != 1:
            raise KeyError(key)
        audit.log(conn, actor, "compliance.confirm", key, {"status": status, "note": note})

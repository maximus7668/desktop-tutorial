"""Pagos con Stripe sin llamar a su API: el propietario crea un Payment Link en su panel de Stripe y lo
asigna al producto; Stripe avisa por webhook firmado. Así el sistema nunca maneja datos de tarjeta ni
claves secretas de la API, solo el secreto del webhook.

Formato de firma (documentación de Stripe, "Verify webhook signatures"): cabecera
Stripe-Signature: t=<timestamp>,v1=<hmac_sha256(secret, f"{t}.{payload}")>."""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from urllib.parse import urlencode, urlparse

from .. import finance, settings_store
from ..actors import Actor
from ..config import Settings
from . import IntegrationError, IntegrationInfo

TOLERANCE_SECONDS = 300


def info(settings: Settings) -> IntegrationInfo:
    ok = bool(settings.stripe_webhook_secret)
    return IntegrationInfo(
        "pagos_stripe", ok, "recibir webhooks firmados; sin acceso a la API ni a datos de tarjeta",
        "Configura STRIPE_WEBHOOK_SECRET (whsec_...) y crea un Payment Link por producto en el panel de Stripe. "
        "Los cobros reales además requieren commerce_authorized=on (checklist legal/fiscal completo).")


def verify_signature(payload: bytes, header: str, secret: str, now: int | None = None) -> None:
    if not secret:
        raise IntegrationError("webhook de Stripe no configurado")
    parts: dict[str, list[str]] = {}
    for item in (header or "").split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        raise IntegrationError("cabecera Stripe-Signature mal formada") from None
    if abs((now or int(time.time())) - ts) > TOLERANCE_SECONDS:
        raise IntegrationError("firma fuera de la ventana de tolerancia")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in parts.get("v1", [])):
        raise IntegrationError("firma de Stripe no válida")


def sign_for_tests(payload: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def checkout_url(payment_link: str, product_id: int) -> str:
    u = urlparse(payment_link)
    if u.scheme != "https" or not (u.hostname or "").endswith("stripe.com"):
        raise IntegrationError("el enlace de pago debe ser un Payment Link https de Stripe")
    sep = "&" if u.query else "?"
    return payment_link + sep + urlencode({"client_reference_id": f"product-{product_id}"})


def handle_webhook(conn: sqlite3.Connection, settings: Settings, actor: Actor, payload: bytes, header: str) -> dict:
    verify_signature(payload, header, settings.stripe_webhook_secret)
    event = json.loads(payload)
    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    # Solo es dinero real si: evento en modo live + entorno de producción + comercio autorizado por el propietario.
    real = bool(event.get("livemode")) and settings.is_production and settings_store.is_on(conn, "commerce_authorized")
    data_kind = "real" if real else "simulation"
    if etype == "checkout.session.completed":
        if obj.get("payment_status") != "paid":
            return {"ignored": "pago no completado"}
        ref = obj.get("client_reference_id") or ""
        product_id = int(ref.split("-", 1)[1]) if ref.startswith("product-") and ref.split("-", 1)[1].isdigit() else None
        if product_id is not None and conn.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone() is None:
            product_id = None
        external_id = obj.get("payment_intent") or obj.get("id")
        if not external_id or not isinstance(obj.get("amount_total"), int):
            raise IntegrationError("evento de pago incompleto")
        order, created = finance.record_order(conn, actor, "stripe", external_id, obj["amount_total"], data_kind,
                                              product_id, (obj.get("currency") or "eur").lower())
        return {"order_id": order["id"], "created": created, "data_kind": data_kind}
    if etype == "charge.refunded":
        pi = obj.get("payment_intent")
        return {"refunded": bool(pi) and finance.record_refund(conn, actor, "stripe", pi)}
    return {"ignored": etype}

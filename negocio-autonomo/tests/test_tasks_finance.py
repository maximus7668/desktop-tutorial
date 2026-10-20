"""Cola de tareas, recuperación tras reinicio, pedidos, ingresos y webhooks."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import finance, settings_store, tasks
from app.actors import PUBLIC
from app.core import bootstrap
from app.integrations import IntegrationError, payments
from app.worker import run_once
from app.integrations.llm import LLMProvider


def test_enqueue_is_idempotent(conn):
    a, new_a = tasks.enqueue(conn, "ops.report", "operaciones", {}, "same")
    b, new_b = tasks.enqueue(conn, "ops.report", "operaciones", {}, "same")
    assert a == b and new_a and not new_b


def test_limited_retries_then_failed(conn):
    tid, _ = tasks.enqueue(conn, "x", "operaciones", {}, "retry", max_attempts=2)
    t = tasks.claim(conn)
    assert tasks.fail(conn, t["id"], "error 1") == "pending"
    conn.execute("UPDATE tasks SET run_after='2000-01-01T00:00:00+00:00' WHERE id=?", (tid,))
    t = tasks.claim(conn)
    assert tasks.fail(conn, t["id"], "error 2") == "failed"
    assert tasks.claim(conn) is None


def test_recovers_running_task_after_crash(settings, conn):
    tid, _ = tasks.enqueue(conn, "ops.watch", "operaciones", {}, "crash")
    t = tasks.claim(conn, lease_seconds=60)
    assert t["id"] == tid
    conn.close()  # "se cae" el proceso con la tarea a medias
    c2 = bootstrap(settings)
    assert tasks.claim(c2) is None  # el lease aún no ha caducado: nadie la duplica
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    c2.execute("UPDATE tasks SET lease_until=? WHERE id=?", (past, tid))
    again = tasks.claim(c2)
    assert again["id"] == tid and again["attempts"] == 2
    c2.close()


def test_pause_and_resume_queue_keeps_state(conn, owner):
    tasks.enqueue(conn, "ops.watch", "operaciones", {}, "p1")
    tasks.set_paused(conn, owner, True)
    assert tasks.claim(conn) is None
    tasks.set_paused(conn, owner, False)
    assert tasks.claim(conn)["idempotency_key"] == "p1"


def test_schedules_do_not_duplicate(conn):
    first = tasks.tick_schedules(conn)
    second = tasks.tick_schedules(conn)
    assert len(first) == len(tasks.DEFAULT_SCHEDULES) and second == []


def test_worker_runs_and_marks_unknown_failures(conn, settings):
    tasks.tick_schedules(conn)
    results = [run_once(conn, settings, LLMProvider()) for _ in range(6)]
    statuses = [r["status"] for r in results if r]
    assert statuses.count("done") == len(tasks.DEFAULT_SCHEDULES)
    tasks.enqueue(conn, "no.existe", "operaciones", {}, "bad")
    r = run_once(conn, settings, LLMProvider())
    assert r["status"] == "failed"


def test_orders_are_not_duplicated_on_retry(conn):
    for _ in range(3):
        finance.record_order(conn, PUBLIC, "stripe", "pi_123", 1900, "real")
    assert conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"] == 1
    assert finance.summary(conn)["real"]["revenue_cents"] == 1900


def test_simulated_sales_are_not_real_revenue(conn):
    finance.record_order(conn, PUBLIC, "stripe", "sim_1", 5000, "simulation")
    s = finance.summary(conn)
    assert s["real"]["revenue_cents"] == 0 and s["simulation"]["revenue_cents"] == 5000
    assert s["operating_profit_cents"] == 0 and s["orders_real"] == 0


def _event(livemode=True, pid=None, pi="pi_live_1", amount=1900):
    return json.dumps({"type": "checkout.session.completed", "livemode": livemode, "data": {"object": {
        "id": "cs_1", "payment_intent": pi, "amount_total": amount, "currency": "eur", "payment_status": "paid",
        "client_reference_id": f"product-{pid}" if pid else None}}}).encode()


def test_webhook_requires_valid_signature(conn, settings):
    settings.stripe_webhook_secret = "whsec_testsecret123"
    body = _event()
    with pytest.raises(IntegrationError):
        payments.handle_webhook(conn, settings, PUBLIC, body, "t=1,v1=bad")
    with pytest.raises(IntegrationError):
        payments.handle_webhook(conn, settings, PUBLIC, body, payments.sign_for_tests(body, "otro"))
    assert conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"] == 0


def test_webhook_in_test_env_is_simulation_and_retry_safe(conn, settings):
    settings.stripe_webhook_secret = "whsec_testsecret123"
    body = _event(livemode=True)
    sig = payments.sign_for_tests(body, settings.stripe_webhook_secret)
    r1 = payments.handle_webhook(conn, settings, PUBLIC, body, sig)
    r2 = payments.handle_webhook(conn, settings, PUBLIC, body, sig)  # Stripe reintenta
    assert r1["data_kind"] == "simulation" and r1["created"] and not r2["created"]
    assert finance.summary(conn)["real"]["revenue_cents"] == 0


def test_webhook_real_only_in_production_with_commerce_authorized(conn, settings, owner):
    from app import compliance

    settings.app_env = "production"
    settings.stripe_webhook_secret = "whsec_testsecret123"
    body = _event(pi="pi_a")
    r = payments.handle_webhook(conn, settings, PUBLIC, body, payments.sign_for_tests(body, settings.stripe_webhook_secret))
    assert r["data_kind"] == "simulation"  # comercio no autorizado aún
    with pytest.raises(PermissionError):
        settings_store.set_value(conn, owner, "commerce_authorized", "on")
    for item in compliance.list_items(conn):
        compliance.confirm(conn, owner, item["key"], "done", "revisado en prueba")
    settings_store.set_value(conn, owner, "commerce_authorized", "on")
    body = _event(pi="pi_b")
    r = payments.handle_webhook(conn, settings, PUBLIC, body, payments.sign_for_tests(body, settings.stripe_webhook_secret))
    assert r["data_kind"] == "real"
    test_mode = _event(livemode=False, pi="pi_c")
    r = payments.handle_webhook(conn, settings, PUBLIC, test_mode,
                                payments.sign_for_tests(test_mode, settings.stripe_webhook_secret))
    assert r["data_kind"] == "simulation"  # modo test de Stripe nunca es dinero real
    assert finance.summary(conn)["real"]["revenue_cents"] == 1900


def test_refund_recorded_once(conn):
    finance.record_order(conn, PUBLIC, "stripe", "pi_r", 1900, "real")
    assert finance.record_refund(conn, PUBLIC, "stripe", "pi_r")
    assert not finance.record_refund(conn, PUBLIC, "stripe", "pi_r")
    s = finance.summary(conn)
    assert s["real"]["refunds_cents"] == -1900 and s["real"]["net_cents"] == 0

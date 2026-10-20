"""API interna y panel de supervisión (FastAPI + plantillas Jinja2 renderizadas en servidor)."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .. import (approvals, audit, budget, compliance, finance, memory, permissions, settings_store, tasks,
                validation)
from ..actors import PUBLIC, PermissionDenied, human
from ..agents import builder, content
from ..config import Settings
from ..core import bootstrap
from ..db import connect, now_iso, one, rows, transaction
from ..integrations import IntegrationError, list_status, payments
from ..untrusted import clean
from . import auth

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["eur"] = lambda c: "—" if c is None else f"{c / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
TEMPLATES.env.filters["fromjson"] = lambda s: json.loads(s) if s else {}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
BOT_RE = re.compile(r"(?i)bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests")


class LoginRequired(Exception):
    pass


def create_app(settings: Settings) -> FastAPI:
    bootstrap(settings).close()
    app = FastAPI(title="Negocio autónomo supervisado", docs_url=None, redoc_url=None, openapi_url=None)
    login_limiter = auth.RateLimiter(5, 900)
    public_limiter = auth.RateLimiter(60, 60)

    def get_conn():
        conn = connect(settings.database_path)
        try:
            yield conn
        finally:
            conn.close()

    def session(request: Request) -> dict:
        s = auth.read_session(request.cookies.get(auth.COOKIE), settings.secret_key)
        if not s:
            raise LoginRequired()
        return s

    def check_csrf(sess: dict, token: str) -> None:
        if not hmac.compare_digest(sess["csrf"], token or ""):
            raise HTTPException(403, "CSRF no válido")

    @app.exception_handler(LoginRequired)
    async def _login_redirect(request: Request, exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(PermissionDenied)
    async def _denied(request: Request, exc: PermissionDenied):
        return PlainTextResponse(str(exc), status_code=403)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'none'; form-action 'self' https://buy.stripe.com"
        return resp

    def page(request: Request, name: str, sess: dict | None, **ctx) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, name, {"sess": sess, "env": settings.app_env, **ctx})

    def back(request: Request, default: str = "/") -> RedirectResponse:
        ref = request.headers.get("referer", "")
        path = re.sub(r"^https?://[^/]+", "", ref) or default
        return RedirectResponse(path if path.startswith("/") else default, status_code=303)

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "0.0.0.0"

    # ------------------------------------------------------------------ público
    @app.get("/healthz")
    def healthz(conn=Depends(get_conn)):
        return {"ok": True, "env": settings.app_env, "kill_switch": settings_store.get(conn, "kill_switch")}

    def _published(conn, slug: str) -> dict:
        p = one(conn, "SELECT * FROM products WHERE slug=? AND status='published'", (slug,))
        if p is None:
            raise HTTPException(404)
        return p

    def _visitor(request: Request) -> str:
        day = datetime.now(timezone.utc).date().isoformat()
        salt = hmac.new(settings.secret_key.encode(), day.encode(), hashlib.sha256).hexdigest()
        raw = f"{salt}|{client_ip(request)}|{request.headers.get('user-agent', '')}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _source(request: Request) -> str:
        """Canal: utm_source de la URL; si no (p. ej. el formulario), el de la página de la que viene;
        si no, el dominio que la enlazó."""
        if request.query_params.get("utm_source"):
            return request.query_params["utm_source"]
        ref = urlparse(request.headers.get("referer", ""))
        utm = parse_qs(ref.query).get("utm_source")
        if utm:
            return utm[0]
        host = ref.hostname or ""
        own = urlparse(settings.public_base_url).hostname or ""
        return "" if host in ("", own, "localhost", "127.0.0.1") or host.endswith("trycloudflare.com") else host

    def _event(conn, product_id: int, etype: str, request: Request) -> None:
        if BOT_RE.search(request.headers.get("user-agent", "")):
            return
        src = clean(_source(request), 60)
        with transaction(conn):
            conn.execute("INSERT INTO events (product_id, ts, type, visitor_hash, source, data_kind) VALUES (?,?,?,?,?,?)",
                         (product_id, now_iso(), etype, _visitor(request), src, settings.live_data_kind))

    def _limit(request: Request) -> None:
        if not public_limiter.hit(client_ip(request)):
            raise HTTPException(429, "Demasiadas peticiones")

    @app.get("/p/{slug}", response_class=HTMLResponse)
    def landing(slug: str, request: Request, conn=Depends(get_conn)):
        _limit(request)
        p = _published(conn, slug)
        _event(conn, p["id"], "visit", request)
        return HTMLResponse(builder.render(conn, settings, p))

    @app.post("/p/{slug}/signup", response_class=HTMLResponse)
    def signup(slug: str, request: Request, email: str = Form(""), consent: str = Form(""), conn=Depends(get_conn)):
        _limit(request)
        p = _published(conn, slug)
        email = email.strip().lower()
        if not EMAIL_RE.match(email) or consent != "yes":
            raise HTTPException(400, "Email no válido o falta el consentimiento")
        with transaction(conn):
            cur = conn.execute("INSERT OR IGNORE INTO signups (product_id, email, consent_text, created_at, data_kind)"
                               " VALUES (?,?,?,?,?)", (p["id"], email, builder.consent_text(settings), now_iso(),
                                                       settings.live_data_kind))
            if cur.rowcount:
                _event(conn, p["id"], "signup", request)
        return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                            "<title>Gracias</title><p style='font:18px system-ui;max-width:600px;margin:40px auto;padding:0 16px'>"
                            "Gracias. Te avisaremos cuando esté disponible. Puedes pedir la baja cuando quieras.</p>")

    @app.get("/p/{slug}/checkout")
    def checkout(slug: str, request: Request, conn=Depends(get_conn)):
        _limit(request)
        p = _published(conn, slug)
        if settings_store.is_on(conn, "kill_switch") or not settings_store.is_on(conn, "commerce_authorized") \
                or not p["payment_link"]:
            return RedirectResponse(f"/p/{slug}", status_code=303)
        _event(conn, p["id"], "checkout_click", request)
        return RedirectResponse(payments.checkout_url(p["payment_link"], p["id"]), status_code=303)

    @app.post("/p/{slug}/inquiry", response_class=HTMLResponse)
    def inquiry(slug: str, request: Request, message: str = Form(""), conn=Depends(get_conn)):
        _limit(request)
        p = _published(conn, slug)
        msg = clean(message, 1000)
        if len(msg) < 3:
            raise HTTPException(400)
        with transaction(conn):
            cur = conn.execute("INSERT INTO inquiries (product_id, message, created_at, data_kind) VALUES (?,?,?,?)",
                               (p["id"], msg, now_iso(), settings.live_data_kind))
            iid = cur.lastrowid
        _event(conn, p["id"], "inquiry", request)
        tasks.enqueue(conn, "sales.inquiry", "ventas", {"inquiry_id": iid}, f"inquiry:{iid}")
        return HTMLResponse("<!doctype html><meta charset=utf-8><title>Recibido</title>"
                            "<p style='font:18px system-ui;max-width:600px;margin:40px auto'>Pregunta recibida.</p>")

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request, conn=Depends(get_conn)):
        payload = await request.body()
        try:
            result = payments.handle_webhook(conn, settings, PUBLIC, payload, request.headers.get("stripe-signature", ""))
        except (IntegrationError, ValueError, json.JSONDecodeError) as e:
            audit.log(conn, PUBLIC, "webhook.rejected", "stripe", {"error": str(e)})
            return JSONResponse({"error": "rechazado"}, status_code=400)
        return result

    @app.get("/legal/{doc}", response_class=HTMLResponse)
    def legal(doc: str, request: Request):
        if doc not in ("aviso-legal", "privacidad"):
            raise HTTPException(404)
        return page(request, f"public/{doc}.html", None, s=settings)

    # ------------------------------------------------------------------ acceso
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "login.html", None, error=None)

    @app.post("/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), conn=Depends(get_conn)):
        if not login_limiter.hit(client_ip(request)):
            return page(request, "login.html", None, error="Demasiados intentos. Espera 15 minutos.")
        if not auth.authenticate(conn, username, password):
            audit.log(conn, PUBLIC, "login.failed", clean(username, 60))
            return page(request, "login.html", None, error="Usuario o contraseña incorrectos.")
        audit.log(conn, human(username), "login.ok")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(auth.COOKIE, auth.make_session(username, settings.secret_key), httponly=True,
                        samesite="strict", secure=settings.is_production, max_age=auth.SESSION_TTL)
        return resp

    @app.post("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(auth.COOKIE)
        return resp

    # ------------------------------------------------------------------ panel
    def _range(request: Request) -> tuple[str | None, str | None]:
        f, t = request.query_params.get("desde") or None, request.query_params.get("hasta") or None
        for v in (f, t):
            if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise HTTPException(400, "fecha no válida (AAAA-MM-DD)")
        return f, t

    def _where_ts(f, t, col="ts"):
        q, p = "", []
        if f:
            q += f" AND {col} >= ?"
            p.append(f)
        if t:
            q += f" AND {col} < ?"
            p.append(t + "T23:59:59~")
        return q, p

    def _funnel(conn, f, t) -> dict:
        q, p = _where_ts(f, t)
        out = {}
        for r in conn.execute("SELECT data_kind, type, COUNT(*) c, COUNT(DISTINCT visitor_hash) u FROM events WHERE 1=1"
                              + q + " GROUP BY data_kind, type", p):
            d = out.setdefault(r["data_kind"], {})
            d[r["type"]] = r["c"]
            if r["type"] == "visit":
                d["unique"] = r["u"]
        for d in out.values():
            d["conversion"] = round(100 * d.get("signup", 0) / d["unique"], 1) if d.get("unique") else 0.0
        return out

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        f, t = _range(request)
        q, p = _where_ts(f, t)
        ctx = {
            "fin": finance.summary(conn, f, t),
            "funnel": _funnel(conn, f, t),
            "agents": rows(conn, "SELECT * FROM agents ORDER BY name"),
            "tasks": tasks.stats(conn),
            "opps": conn.execute("SELECT COUNT(*) c FROM opportunities").fetchone()["c"],
            "products": {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM products GROUP BY status")},
            "pending": approvals.pending(conn),
            "alerts": rows(conn, "SELECT * FROM alerts WHERE acknowledged=0 ORDER BY id DESC LIMIT 20"),
            "decisions": rows(conn, "SELECT * FROM audit_log WHERE action NOT LIKE 'use:%'" + q + " ORDER BY id DESC LIMIT 25", tuple(p)),
            "mode": settings_store.get(conn, "mode"),
            "kill": settings_store.is_on(conn, "kill_switch"),
            "commerce": settings_store.is_on(conn, "commerce_authorized"),
            "queue_paused": settings_store.is_on(conn, "queue_paused"),
            "desde": f or "", "hasta": t or "",
        }
        return page(request, "dashboard.html", sess, **ctx)

    @app.get("/aprobaciones", response_class=HTMLResponse)
    def approvals_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        return page(request, "approvals.html", sess, pending=approvals.pending(conn), recent=approvals.list_recent(conn, 50))

    @app.post("/aprobaciones/{aid}")
    def decide(aid: int, request: Request, decision: str = Form(...), note: str = Form(""), csrf: str = Form(""),
               sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        try:
            approvals.decide(conn, human(sess["u"]), aid, decision == "approve", clean(note, 500))
        except (ValueError, PermissionError, KeyError) as e:
            return PlainTextResponse(f"No se pudo aplicar: {e}", status_code=409)
        return RedirectResponse("/aprobaciones", status_code=303)

    @app.get("/oportunidades", response_class=HTMLResponse)
    def opps(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        items = rows(conn, "SELECT * FROM opportunities ORDER BY COALESCE(score,-1) DESC")
        for o in items:
            o["evidence"] = rows(conn, "SELECT * FROM evidence WHERE opportunity_id=?", (o["id"],))
        return page(request, "opportunities.html", sess, items=items)

    @app.get("/experimentos", response_class=HTMLResponse)
    def exps(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        items = rows(conn, "SELECT e.*, o.title FROM experiments e JOIN opportunities o ON o.id=e.opportunity_id ORDER BY e.id DESC")
        for e in items:
            e["live"] = validation.metrics(conn, e["id"], "real")
            e["sim"] = validation.metrics(conn, e["id"], "simulation")
        return page(request, "experiments.html", sess, items=items)

    @app.get("/productos", response_class=HTMLResponse)
    def products(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        return page(request, "products.html", sess, items=rows(conn, "SELECT * FROM products ORDER BY id DESC"))

    @app.get("/productos/{pid}/vista-previa", response_class=HTMLResponse)
    def preview(pid: int, sess=Depends(session), conn=Depends(get_conn)):
        p = one(conn, "SELECT * FROM products WHERE id=?", (pid,))
        if p is None:
            raise HTTPException(404)
        return HTMLResponse(builder.render(conn, settings, p))

    def _table(request, sess, title, data, note=""):
        cols = list(data[0].keys()) if data else []
        return page(request, "table.html", sess, title=title, cols=cols, data=data, note=note,
                    desde=request.query_params.get("desde", ""), hasta=request.query_params.get("hasta", ""))

    @app.get("/tareas", response_class=HTMLResponse)
    def tasks_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        data = rows(conn, "SELECT id, type, agent, status, attempts, max_attempts, run_after, last_error, updated_at FROM tasks ORDER BY id DESC LIMIT 300")
        sch = rows(conn, "SELECT * FROM schedules ORDER BY name")
        return page(request, "tasks.html", sess, data=data, schedules=sch, handlers=sorted(_MANUAL_TASKS))

    @app.post("/tareas/encolar")
    def enqueue(request: Request, task_type: str = Form(...), payload: str = Form("{}"), csrf: str = Form(""),
                sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        if task_type not in _MANUAL_TASKS:
            raise HTTPException(400)
        try:
            data = json.loads(payload or "{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "payload JSON no válido") from None
        key = f"manual:{task_type}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}:{secrets.token_hex(4)}"
        tasks.enqueue(conn, task_type, _MANUAL_TASKS[task_type], data, key)
        audit.log(conn, human(sess["u"]), "task.enqueue", task_type, data)
        return RedirectResponse("/tareas", status_code=303)

    @app.get("/finanzas", response_class=HTMLResponse)
    def finance_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        f, t = _range(request)
        return page(request, "finance.html", sess, fin=finance.summary(conn, f, t), ledger=finance.ledger(conn, f, t),
                    spends=budget.list_requests(conn), orders=rows(conn, "SELECT * FROM orders ORDER BY id DESC"),
                    llm=rows(conn, "SELECT * FROM llm_usage ORDER BY id DESC LIMIT 100"), desde=f or "", hasta=t or "",
                    floor_pct=settings_store.get(conn, "reserve_floor_pct"))

    @app.post("/finanzas/capital")
    def add_capital(request: Request, euros: str = Form(...), note: str = Form(""), csrf: str = Form(""),
                    sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        try:
            cents = round(float(euros.replace(",", ".")) * 100)
            budget.add_capital(conn, human(sess["u"]), cents, clean(note, 300))
        except ValueError as e:
            return PlainTextResponse(f"No se pudo aportar: {e}", status_code=400)
        return RedirectResponse("/finanzas", status_code=303)

    @app.get("/auditoria", response_class=HTMLResponse)
    def audit_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        f, t = _range(request)
        q, p = _where_ts(f, t)
        ok, broken = audit.verify_chain(conn)
        data = rows(conn, "SELECT id, ts, actor_kind, actor, action, target, details FROM audit_log WHERE 1=1" + q
                    + " ORDER BY id DESC LIMIT 500", tuple(p))
        return _table(request, sess, "Registro de auditoría", data,
                      "Cadena íntegra ✔" if ok else f"⚠ Cadena alterada en el registro {broken}")

    @app.get("/memoria", response_class=HTMLResponse)
    def memory_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        return _table(request, sess, "Memoria (investigaciones, decisiones, lecciones)", memory.recall(conn, None, 300))

    @app.get("/contenido", response_class=HTMLResponse)
    def content_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        drafts = rows(conn, "SELECT d.*, p.name AS producto FROM content_drafts d JOIN products p ON p.id=d.product_id"
                            " ORDER BY CASE d.status WHEN 'draft' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, d.id DESC")
        for d in drafts:
            d["text"] = content.render_body(d, settings.public_base_url)
        return page(request, "content.html", sess, drafts=drafts, base_url=settings.public_base_url,
                    real=content.visits_by_channel(conn, "real"), sim=content.visits_by_channel(conn, "simulation"),
                    published=rows(conn, "SELECT id, name FROM products WHERE status='published'"))

    @app.post("/contenido/{did}")
    def content_decide(did: int, request: Request, status: str = Form(...), published_url: str = Form(""),
                       csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        try:
            content.decide(conn, human(sess["u"]), did, status, published_url)
        except (ValueError, KeyError) as e:
            return PlainTextResponse(f"No se pudo: {e}", status_code=409)
        return RedirectResponse("/contenido", status_code=303)

    @app.post("/contenido/generar/{pid}")
    def content_generate(pid: int, request: Request, csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        key = f"manual:content:{pid}:{secrets.token_hex(4)}"
        tasks.enqueue(conn, "content.drafts", content.AGENT, {"product_id": pid}, key)
        audit.log(conn, human(sess["u"]), "task.enqueue", "content.drafts", {"product_id": pid})
        return RedirectResponse("/contenido", status_code=303)

    @app.get("/consultas", response_class=HTMLResponse)
    def inquiries_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        return _table(request, sess, "Consultas", rows(conn, "SELECT * FROM inquiries ORDER BY id DESC"))

    @app.get("/ajustes", response_class=HTMLResponse)
    def settings_page(request: Request, sess=Depends(session), conn=Depends(get_conn)):
        vals = {k: settings_store.get(conn, k) for k in settings_store.DEFAULTS}
        return page(request, "settings.html", sess, vals=vals, perms=permissions.list_all(conn),
                    catalog=sorted(f"{t}.{a}" for t, a in permissions.CATALOG), agents=sorted(permissions.AGENT_ROLES),
                    compliance=compliance.list_items(conn), integrations=list_status(conn),
                    products=rows(conn, "SELECT id, name, payment_link FROM products"),
                    schedules=rows(conn, "SELECT * FROM schedules"))

    @app.post("/ajustes/parada")
    def kill(request: Request, state: str = Form(...), csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        h = human(sess["u"])
        if state == "on":
            settings_store.activate_kill_switch(conn, h, "activada desde el panel")
        else:
            settings_store.release_kill_switch(conn, h)
        return back(request)

    @app.post("/ajustes/valor")
    def set_value(request: Request, key: str = Form(...), value: str = Form(...), csrf: str = Form(""),
                  sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        try:
            settings_store.set_value(conn, human(sess["u"]), key, value.strip())
        except (KeyError, ValueError, PermissionError) as e:
            return PlainTextResponse(f"No se pudo cambiar: {e}", status_code=409)
        return back(request, "/ajustes")

    @app.post("/ajustes/permiso")
    def set_perm(request: Request, agent_name: str = Form(...), tool_action: str = Form(...), policy: str = Form(...),
                 daily_limit: str = Form(""), csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        tool, _, action = tool_action.partition(".")
        try:
            permissions.set_permission(conn, human(sess["u"]), agent_name, tool, action, policy,
                                       int(daily_limit) if daily_limit.strip() else None)
        except (ValueError, PermissionError) as e:
            return PlainTextResponse(f"No se pudo cambiar: {e}", status_code=409)
        return back(request, "/ajustes")

    @app.post("/ajustes/cumplimiento")
    def set_compliance(request: Request, key: str = Form(...), status: str = Form(...), note: str = Form(""),
                       csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        compliance.confirm(conn, human(sess["u"]), key, status, clean(note, 500))
        return back(request, "/ajustes")

    @app.post("/ajustes/enlace-pago")
    def set_link(request: Request, product_id: int = Form(...), link: str = Form(...), csrf: str = Form(""),
                 sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        try:
            builder.set_payment_link(conn, human(sess["u"]), product_id, link.strip())
        except IntegrationError as e:
            return PlainTextResponse(str(e), status_code=400)
        return back(request, "/ajustes")

    @app.post("/ajustes/programacion")
    def set_schedule(request: Request, name: str = Form(...), enabled: str = Form(...), csrf: str = Form(""),
                     sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        tasks.set_schedule_enabled(conn, human(sess["u"]), name, enabled == "1")
        return back(request, "/ajustes")

    @app.post("/alertas/{aid}/ok")
    def ack(aid: int, request: Request, csrf: str = Form(""), sess=Depends(session), conn=Depends(get_conn)):
        check_csrf(sess, csrf)
        with transaction(conn):
            conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (aid,))
        audit.log(conn, human(sess["u"]), "alert.ack", f"alert:{aid}")
        return back(request)

    EXPORTS = {
        "libro": ("SELECT * FROM ledger WHERE 1=1", "ts"),
        "auditoria": ("SELECT id, ts, actor_kind, actor, action, target, details FROM audit_log WHERE 1=1", "ts"),
        "eventos": ("SELECT id, product_id, ts, type, source, data_kind FROM events WHERE 1=1", "ts"),
        "oportunidades": ("SELECT * FROM opportunities WHERE 1=1", "created_at"),
        "experimentos": ("SELECT * FROM experiments WHERE 1=1", "created_at"),
        "gastos": ("SELECT * FROM spend_requests WHERE 1=1", "created_at"),
        "pedidos": ("SELECT * FROM orders WHERE 1=1", "created_at"),
    }

    @app.get("/exportar/{name}.{fmt}")
    def export(name: str, fmt: str, request: Request, sess=Depends(session), conn=Depends(get_conn)):
        if name not in EXPORTS or fmt not in ("csv", "json"):
            raise HTTPException(404)
        f, t = _range(request)
        base, col = EXPORTS[name]
        q, p = _where_ts(f, t, col)
        data = rows(conn, base + q + " ORDER BY id", tuple(p))
        audit.log(conn, human(sess["u"]), "export", name, {"desde": f, "hasta": t, "rows": len(data)})
        if fmt == "json":
            return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
        buf = io.StringIO()
        if data:
            w = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    return app


_MANUAL_TASKS = {
    "director.cycle": "director",
    "research.discover": "investigador",
    "ops.report": "operaciones",
    "ops.backup": "operaciones",
    "ops.watch": "operaciones",
}

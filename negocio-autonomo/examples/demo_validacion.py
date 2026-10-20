"""Ejemplo completo: investigación real → evaluación → experimento → página → tráfico SIMULADO → veredicto.

Se ejecuta en una BD de pruebas aparte (data/demo.db). Las aprobaciones las firma un actor humano de demo
para enseñar el flujo; en uso real las decide el propietario desde el panel.

    python examples/demo_validacion.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import approvals, compliance, finance, validation  # noqa: E402
from app.actors import PUBLIC, agent, human  # noqa: E402
from app.agents import director, researcher  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core import bootstrap  # noqa: E402
from app.db import now_iso, one, rows  # noqa: E402
from app.integrations.llm import LLMProvider  # noqa: E402
from app.worker import run_once  # noqa: E402


def main() -> None:
    db = ROOT / "data" / "demo.db"
    for f in db.parent.glob("demo.db*"):
        f.unlink()
    settings = Settings(app_env="test", database_path=db, secret_key="demo-no-usar-en-produccion",
                        owner_legal_name="Titular de demostración", owner_contact_email="demo@example.com",
                        reports_dir=ROOT / "reports", backup_dir=ROOT / "backups")
    conn = bootstrap(settings)
    owner = human("propietario-demo")
    out: list[str] = ["# Ejemplo de creación y validación de un producto (ejecución real del sistema, tráfico simulado)\n",
                      f"Generado: {now_iso()} · entorno: test · BD: data/demo.db\n"]

    data = json.loads((ROOT / "examples" / "investigacion_2026-10-20.json").read_text(encoding="utf-8"))
    imp = researcher.import_research(conn, agent("investigador"), data)
    out.append(f"## 1. Investigación importada\n\nOportunidades creadas: {imp['created']} (fuentes reales, ver "
               "`examples/investigacion_2026-10-20.json`).\n")

    cyc = director.cycle(conn, agent("director"))
    out.append("## 2. Evaluación y decisión del director\n")
    out.append("| # | Oportunidad | Puntuación | Fuentes indep. | Avisos |\n|---|---|---|---|---|")
    for o in rows(conn, "SELECT * FROM opportunities ORDER BY score DESC"):
        b = json.loads(o["score_breakdown"])
        out.append(f"| {o['id']} | {o['title']} | {o['score']} | {b['independent_sources']} | {'; '.join(b['notes']) or '—'} |")
    out.append(f"\nAcciones del director: {cyc['actions']}\n")

    pend = approvals.pending(conn)
    if not pend:
        out.append(f"**Ninguna oportunidad supera el umbral de {director.MIN_SCORE} puntos.** El sistema no propone "
                   "experimentos: hace falta mejor evidencia (p. ej. entrevistas o búsquedas de palabras clave con volumen).\n")
        # Para enseñar el resto del flujo, el propietario elige manualmente la mejor (decisión humana registrada).
        best = one(conn, "SELECT * FROM opportunities ORDER BY score DESC LIMIT 1")
        out.append(f"Para la demostración, el propietario elige a mano la mejor: «{best['title']}» "
                   f"({best['score']} puntos). Esta decisión queda en auditoría como humana.\n")
        validation.propose(conn, agent("director"), best["id"])
        pend = approvals.pending(conn)
    exp_ap = pend[0]
    out.append(f"## 3. Experimento propuesto (pendiente de aprobación)\n\n> {exp_ap['summary']}\n")
    approvals.decide(conn, owner, exp_ap["id"], True, "demo: aprobado por el propietario")
    exp = one(conn, "SELECT * FROM experiments ORDER BY id DESC LIMIT 1")
    out.append(f"- Hipótesis: {exp['hypothesis']}\n- Diseño: {exp['design']}\n- Éxito si: {exp['success_metric']} ≥ "
               f"{exp['success_threshold']} con ≥ {exp['min_visits']} visitantes en {exp['duration_days']} días\n"
               f"- Presupuesto máximo: {exp['max_budget_cents'] / 100:.2f} € (sin gasto previsto: tráfico orgánico)\n"
               f"- Criterios bloqueados: {exp['criteria_locked_at']}\n")

    while run_once(conn, settings, LLMProvider()):
        pass
    p = one(conn, "SELECT * FROM products ORDER BY id DESC LIMIT 1")
    checks = json.loads(p["checks"])
    out.append(f"## 4. Página generada y validada técnicamente\n\nProducto #{p['id']} «{p['name']}» → estado `{p['status']}`.\n")
    out.append("| Comprobación | Resultado |\n|---|---|")
    out += [f"| {k} | {'OK' if v else 'FALLA'} |" for k, v in checks["checks"].items()]
    (ROOT / "examples" / "landing_ejemplo.html").write_text(p["html"], encoding="utf-8")
    out.append("\nHTML guardado en `examples/landing_ejemplo.html`.\n")

    pub = next(a for a in approvals.pending(conn) if a["kind"] == "product.publish")
    try:
        approvals.decide(conn, owner, pub["id"], True)
    except PermissionError as e:
        out.append(f"## 5. Publicación\n\nPrimer intento bloqueado: _{e}_\n")
        for item in compliance.list_items(conn):
            if item["required_for"] == "publish":
                compliance.confirm(conn, owner, item["key"], "done", "demo (entorno de pruebas)")
        approvals.decide(conn, owner, pub["id"], True)
        out.append("Tras confirmar el checklist de publicación (solo en demo), la página se publica y el experimento empieza.\n")

    rnd = random.Random(42)
    for i in range(140):
        conn.execute("INSERT INTO events (product_id, ts, type, visitor_hash, data_kind) VALUES (?,?,?,?,?)",
                     (p["id"], now_iso(), "visit", f"sim{i}", "simulation"))
        if rnd.random() < 0.11:
            conn.execute("INSERT INTO events (product_id, ts, type, visitor_hash, data_kind) VALUES (?,?,?,?,?)",
                         (p["id"], now_iso(), "signup", f"sim{i}", "simulation"))
    finance.record_order(conn, PUBLIC, "stripe", "demo-sim-1", p["price_cents"] or 1500, "simulation", p["id"])
    conn.execute("UPDATE experiments SET ends_at='2000-01-01T00:00:00+00:00' WHERE id=?", (exp["id"],))
    res = validation.evaluate(conn, agent("director"), exp["id"])
    out.append("## 6. Medición y veredicto\n")
    out.append(f"- Datos **reales**: {res['real']}\n- Datos **simulados** (no cuentan): {res['simulation']}\n"
               f"- Veredicto: **{res['verdict']}** → decisión **{res['decision']}**\n- {res['conclusion']}\n")
    fin = finance.summary(conn)
    out.append(f"## 7. Finanzas tras la demo\n\n- Ingresos reales: {fin['real']['revenue_cents'] / 100:.2f} €\n"
               f"- Ingresos simulados (no son ingresos): {fin['simulation']['revenue_cents'] / 100:.2f} €\n"
               f"- Disponible: {fin['budget']['available_cents'] / 100:.2f} € de {fin['budget']['capital_cents'] / 100:.2f} €\n")
    out.append("## 8. Qué haría falta para validar de verdad\n\n1. Completar el checklist legal y desplegar en un dominio "
               "real (APP_ENV=production).\n2. Llevar tráfico orgánico real (≥ 100 visitantes únicos).\n3. Si hay interés, "
               "activar cobros (checklist fiscal + Stripe) y repetir con compra real: solo eso valida.\n")
    report = ROOT / "docs" / "ejemplo-validacion.md"
    report.write_text("\n".join(out), encoding="utf-8")
    print(report.read_text(encoding="utf-8"))
    conn.close()


if __name__ == "__main__":
    main()

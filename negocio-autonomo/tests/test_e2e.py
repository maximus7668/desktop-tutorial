"""Prueba completa de extremo a extremo por HTTP con datos ficticios."""
from fastapi.testclient import TestClient

from app import approvals, compliance
from app.actors import agent
from app.agents import researcher
from app.core import bootstrap
from app.db import one
from app.integrations.llm import LLMProvider
from app.web import auth
from app.web.app import create_app
from app.worker import run_once

from .fixtures import research_fixture


def test_full_cycle(settings):
    settings.initial_capital_eur = 0  # escenario real: se empieza sin dinero
    app = create_app(settings)
    conn = bootstrap(settings)
    auth.create_user(conn, "propietario", "una-contraseña-larga-de-prueba")
    c = TestClient(app)

    # 1. Sin sesión no hay panel; contraseña incorrecta falla
    assert c.get("/", follow_redirects=False).status_code == 303
    assert "incorrectos" in c.post("/login", data={"username": "propietario", "password": "mala-mala-mala"}).text
    r = c.post("/login", data={"username": "propietario", "password": "una-contraseña-larga-de-prueba"},
               follow_redirects=False)
    assert r.status_code == 303
    csrf = auth.read_session(c.cookies.get(auth.COOKIE), settings.secret_key)["csrf"]

    # 2. Investigación (ficticia) importada y ciclo del director desde el panel
    researcher.import_research(conn, agent("investigador"), research_fixture())
    assert c.post("/tareas/encolar", data={"task_type": "director.cycle", "payload": "{}", "csrf": "malo"}).status_code == 403
    c.post("/tareas/encolar", data={"task_type": "director.cycle", "payload": "{}", "csrf": csrf})
    while run_once(conn, settings, LLMProvider()):
        pass
    pend = approvals.pending(conn)
    assert len(pend) == 1 and pend[0]["kind"] == "experiment.start"

    # 3. El propietario aprueba el experimento → se construye la página y se pide publicar
    c.post(f"/aprobaciones/{pend[0]['id']}", data={"decision": "approve", "csrf": csrf})
    while run_once(conn, settings, LLMProvider()):
        pass
    product = one(conn, "SELECT * FROM products")
    assert product["status"] == "tested", product["checks"]
    pub = approvals.pending(conn)[0]
    assert pub["kind"] == "product.publish"
    assert c.get(f"/p/{product['slug']}").status_code == 404  # aún no publicada

    # 4. Publicar sin checklist legal → rechazado; tras confirmarlo → publicada
    r = c.post(f"/aprobaciones/{pub['id']}", data={"decision": "approve", "csrf": csrf})
    assert r.status_code == 409 and "privacy_policy" in r.text
    for item in compliance.list_items(conn):
        if item["required_for"] == "publish":
            c.post("/ajustes/cumplimiento", data={"key": item["key"], "status": "done", "note": "revisado", "csrf": csrf})
    assert c.post(f"/aprobaciones/{pub['id']}", data={"decision": "approve", "csrf": csrf}).status_code == 200
    assert one(conn, "SELECT status FROM products")["status"] == "published"
    assert one(conn, "SELECT status FROM experiments")["status"] == "running"

    # 5. Tráfico simulado: visitas, registros con consentimiento, consulta
    page = c.get(f"/p/{product['slug']}", headers={"user-agent": "Mozilla/5.0 test"})
    assert page.status_code == 200 and "IVA incluido" in page.text and "no se cobra nada" in page.text
    assert "pierden tiempo" not in page.text  # el análisis interno de la oportunidad no se publica
    for i in range(30):
        c.get(f"/p/{product['slug']}", headers={"user-agent": f"Mozilla/5.0 visitante-{i}"})
    c.get(f"/p/{product['slug']}", headers={"user-agent": "Googlebot/2.1"})  # los bots no cuentan
    assert c.post(f"/p/{product['slug']}/signup", data={"email": "a@example.com"}).status_code == 400  # sin consentimiento
    for i in range(5):
        c.post(f"/p/{product['slug']}/signup", data={"email": f"persona{i}@example.com", "consent": "yes"},
               headers={"user-agent": f"Mozilla/5.0 visitante-{i}"})
    c.post(f"/p/{product['slug']}/signup", data={"email": "persona0@example.com", "consent": "yes"})  # duplicado
    c.post(f"/p/{product['slug']}/inquiry", data={"message": "¿Cuánto cuesta?"})
    while run_once(conn, settings, LLMProvider()):
        pass
    ev = {r["type"]: r["c"] for r in conn.execute("SELECT type, COUNT(*) c FROM events WHERE data_kind='simulation' GROUP BY type")}
    assert ev["visit"] == 31 and ev["signup"] == 5
    assert conn.execute("SELECT COUNT(*) c FROM events WHERE data_kind='real'").fetchone()["c"] == 0
    assert one(conn, "SELECT status FROM inquiries")["status"] == "answered_draft"
    # Sin comercio autorizado no hay checkout
    assert c.get(f"/p/{product['slug']}/checkout", follow_redirects=False).headers["location"] == f"/p/{product['slug']}"

    # 6. Fin del plazo: el veredicto ignora la simulación
    conn.execute("UPDATE experiments SET ends_at='2000-01-01T00:00:00+00:00'")
    c.post("/tareas/encolar", data={"task_type": "director.cycle", "payload": "{}", "csrf": csrf})
    while run_once(conn, settings, LLMProvider()):
        pass
    exp = one(conn, "SELECT * FROM experiments")
    assert exp["verdict"] == "datos_insuficientes" and exp["decision"] == "modify"

    # 7. Panel, exportación y auditoría
    dash = c.get("/")
    assert dash.status_code == 200 and "Capital aportado" in dash.text and "sin capital" in dash.text
    # Mes siguiente: el propietario aporta 300 € desde el panel
    assert c.post("/finanzas/capital", data={"euros": "300", "note": "aportación", "csrf": "malo"}).status_code == 403
    c.post("/finanzas/capital", data={"euros": "300", "note": "aportación noviembre", "csrf": csrf})
    dash = c.get("/")
    assert "300,00 €" in dash.text and "240,00 €" in dash.text  # disponible = 300 € - 20 % de suelo
    for path in ("/oportunidades", "/experimentos", "/productos", "/finanzas", "/tareas", "/auditoria", "/memoria",
                 "/ajustes", "/consultas", "/legal/privacidad", "/legal/aviso-legal", "/healthz"):
        assert c.get(path).status_code == 200, path
    csv = c.get("/exportar/eventos.csv?desde=2000-01-01")
    assert csv.status_code == 200 and "visit" in csv.text
    assert "Cadena íntegra" in c.get("/auditoria").text

    # 8. Parada de emergencia desde el panel
    c.post("/ajustes/parada", data={"state": "on", "csrf": csrf})
    assert c.get("/healthz").json()["kill_switch"] == "on"
    c.post("/tareas/encolar", data={"task_type": "ops.report", "payload": "{}", "csrf": csrf})
    assert run_once(conn, settings, LLMProvider()) is None
    conn.close()

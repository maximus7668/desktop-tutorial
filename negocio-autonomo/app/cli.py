"""Línea de órdenes del propietario.

  python -m app.cli init                     crea/migra la BD y datos base
  python -m app.cli create-admin USUARIO     crea o cambia la contraseña de un administrador (la pide por teclado)
  python -m app.cli import-research FICHERO  importa una investigación en JSON
  python -m app.cli validate-research FICHERO comprueba un JSON de investigación sin importarlo
  python -m app.cli import-inbox             importa lo nuevo de investigaciones/entrada/
  python -m app.cli evaluate                 evalúa oportunidades nuevas
  python -m app.cli worker                   arranca el trabajador (cola + programación)
  python -m app.cli run-once                 procesa una sola tarea
  python -m app.cli status                   resumen en texto
  python -m app.cli approvals                 lista las aprobaciones pendientes
  python -m app.cli approve|reject ID [QUIEN] [nota]  decide una aprobación en nombre de QUIEN
  python -m app.cli compliance                lista el checklist legal/fiscal
  python -m app.cli confirm CLAVE|publish QUIEN [nota]  confirma requisitos revisados por el propietario
  python -m app.cli add-capital EUROS [nota] aportar dinero (queda en el libro contable)
  python -m app.cli stop "motivo"            parada de emergencia
  python -m app.cli backup                   copia de seguridad ahora
  python -m app.cli restore FICHERO          restaura una copia (con el sistema parado)
  python -m app.cli verify-audit             comprueba la cadena de auditoría
  python -m app.cli serve                    arranca el panel web (uvicorn)
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import shutil
import sys

from . import approvals, audit, budget, compliance, finance, settings_store, tasks
from .actors import agent, human
from .agents import evaluator, operations, researcher
from .config import load_settings
from .core import bootstrap
from .integrations.llm import build_provider
from .web import auth


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    settings = load_settings()

    if cmd == "restore":
        src = args[0]
        if os.path.exists(settings.database_path):
            shutil.copy2(settings.database_path, str(settings.database_path) + ".antes-de-restaurar")
        for ext in ("-wal", "-shm"):
            p = str(settings.database_path) + ext
            if os.path.exists(p):
                os.remove(p)
        shutil.copy2(src, settings.database_path)
        conn = bootstrap(settings)
        ok, broken = audit.verify_chain(conn)
        print(f"Restaurado desde {src}. Auditoría íntegra: {ok}" + ("" if ok else f" (rota en {broken})"))
        return 0

    conn = bootstrap(settings)
    if cmd == "init":
        print(f"BD lista en {settings.database_path} (entorno {settings.app_env})")
    elif cmd == "create-admin":
        user = args[0]
        pw = os.environ.get("ADMIN_PASSWORD") if settings.app_env == "test" and os.environ.get("ADMIN_PASSWORD") else None
        if pw is None:
            pw = getpass.getpass("Contraseña (mín. 12 caracteres): ")
            if pw != getpass.getpass("Repite la contraseña: "):
                print("No coinciden")
                return 1
        auth.create_user(conn, user, pw)
        print(f"Administrador '{user}' listo")
    elif cmd == "import-research":
        with open(args[0], encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(researcher.import_research(conn, agent("investigador"), data), ensure_ascii=False, indent=2))
    elif cmd == "validate-research":
        # Comprueba un JSON de investigación sin tocar la BD (lo usa la sesión programada antes de subirlo).
        from pydantic import ValidationError
        with open(args[0], encoding="utf-8-sig") as f:
            data = json.load(f)
        try:
            r = researcher.ResearchIn.model_validate(data)
        except ValidationError as e:
            print(f"NO VÁLIDO:\n{e}")
            return 2
        print(f"Válido: run_id={r.run_id}, {len(r.opportunities)} oportunidades, "
              f"{sum(len(o.evidence) for o in r.opportunities)} evidencias")
    elif cmd == "import-inbox":
        print(json.dumps(researcher.import_inbox(conn, agent("investigador")), ensure_ascii=False, indent=2))
    elif cmd == "evaluate":
        for r in evaluator.evaluate_all_new(conn, agent("evaluador")):
            print(f"#{r['id']}: {r['score']}  {r['notes']}")
    elif cmd == "worker":
        from .worker import run_forever
        run_forever(conn, settings, build_provider(settings))
    elif cmd == "run-once":
        from .worker import run_once
        print(run_once(conn, settings, build_provider(settings)))
    elif cmd == "enqueue":
        ttype, ag = args[0], args[1]
        payload = json.loads(args[2]) if len(args) > 2 else {}
        print(tasks.enqueue(conn, ttype, ag, payload, args[3] if len(args) > 3 else f"cli:{ttype}:{os.getpid()}"))
    elif cmd == "approvals":
        for a in approvals.pending(conn):
            print(f"#{a['id']} [{a['kind']}] {a['summary']}")
    elif cmd in ("approve", "reject"):
        # Decisión del propietario tomada fuera del panel (p. ej. por chat); queda firmada con su nombre.
        aid, by = int(args[0]), (args[1] if len(args) > 1 else getpass.getuser())
        note = " ".join(args[2:]) or "decisión registrada por línea de órdenes"
        approvals.decide(conn, human(by), aid, cmd == "approve", note)
        print(f"Aprobación #{aid}: {'aprobada' if cmd == 'approve' else 'rechazada'} por {by}")
    elif cmd == "compliance":
        for c in compliance.list_items(conn):
            print(f"{c['key']:20} [{c['required_for']}] {c['status']:15} {c['title']}")
    elif cmd == "confirm":
        # confirm CLAVE|publish|commerce QUIEN [nota]: el propietario confirma requisitos legales revisados
        target, by = args[0], args[1]
        note = " ".join(args[2:]) or "confirmado por línea de órdenes"
        keys = [c["key"] for c in compliance.list_items(conn)
                if target in ("publish", "commerce") and c["required_for"] == target] or [target]
        for k in keys:
            compliance.confirm(conn, human(by), k, "done", note)
            print(f"{k}: confirmado por {by}")
    elif cmd == "add-capital":
        euros = float(args[0].replace(",", "."))
        bal = budget.add_capital(conn, human(getpass.getuser()), round(euros * 100), " ".join(args[1:]))
        print(f"Capital: {bal['capital_cents'] / 100:.2f} € · disponible para gastar: {bal['available_cents'] / 100:.2f} €")
    elif cmd == "status":
        print(json.dumps({"mode": settings_store.get(conn, "mode"), "kill_switch": settings_store.get(conn, "kill_switch"),
                          "budget": budget.balance(conn), "tasks": tasks.stats(conn),
                          "finance": {k: v for k, v in finance.summary(conn).items() if k in ("real", "simulation", "estimate")}},
                         ensure_ascii=False, indent=2))
    elif cmd == "stop":
        settings_store.activate_kill_switch(conn, human(getpass.getuser()), " ".join(args) or "parada desde CLI")
        print("Parada de emergencia ACTIVADA. Para quitarla: panel → Ajustes → Reanudar.")
    elif cmd == "backup":
        print(operations.backup(conn, agent("operaciones"), settings))
    elif cmd == "verify-audit":
        ok, broken = audit.verify_chain(conn)
        print("Cadena íntegra" if ok else f"Cadena ALTERADA en el registro {broken}")
        return 0 if ok else 2
    elif cmd == "serve":
        import uvicorn

        from .web.app import create_app
        uvicorn.run(create_app(settings), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")),
                    proxy_headers=True)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

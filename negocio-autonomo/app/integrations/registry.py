"""Estado de todas las integraciones para el panel."""
from __future__ import annotations

import sqlite3

from ..config import Settings
from . import IntegrationInfo, record_status
from . import email as email_mod
from . import payments
from .llm import build_provider

PENDING = [
    IntegrationInfo("anuncios", False, "ninguno (solo borradores de campaña)",
                    "Pendiente: adaptador de Google Ads / Meta Ads. Todo gasto publicitario requiere aprobación."),
    IntegrationInfo("plataforma_productos_digitales", False, "ninguno",
                    "Pendiente: adaptador para Gumroad/Lemon Squeezy/Stripe Products si se elige uno."),
    IntegrationInfo("almacenamiento_archivos", True, "escritura en carpetas locales reports/ y backups/",
                    "Local. Para nube: montar un volumen o configurar copia externa de backups/."),
    IntegrationInfo("seguimiento_tareas_externo", False, "ninguno",
                    "Opcional: la cola interna ya persiste tareas; adaptador a Linear/Trello/GitHub Issues pendiente."),
]


def refresh(conn: sqlite3.Connection, settings: Settings) -> None:
    try:
        llm_info = build_provider(settings).info()
    except Exception as e:  # p. ej. paquete anthropic no instalado
        llm_info = IntegrationInfo("llm", False, "llm.complete", f"No se pudo iniciar el proveedor: {type(e).__name__}")
    record_status(conn, llm_info)
    search = IntegrationInfo(
        "busqueda_web", llm_info.configured and settings.llm_provider == "anthropic",
        "web.search vía herramienta web_search del servidor de Anthropic; solo lectura",
        "Requiere LLM_PROVIDER=anthropic. Alternativa sin coste: importar investigación (JSON con fuentes).")
    record_status(conn, search)
    record_status(conn, payments.info(settings))
    record_status(conn, email_mod.info())
    record_status(conn, IntegrationInfo("analitica_propia", True, "registro de visitas/registros sin cookies",
                                        "Integrada en la app: /p/<slug>. Datos reales solo con APP_ENV=production."))
    public = not any(h in settings.public_base_url for h in ("localhost", "127.0.0.1"))
    record_status(conn, IntegrationInfo("publicacion_web", public, "servir páginas aprobadas en /p/<slug>",
                                        "Despliega la app en un dominio con HTTPS y define PUBLIC_BASE_URL."))
    record_status(conn, IntegrationInfo("base_de_datos", True, "SQLite local (WAL)", str(settings.database_path.name)))
    from . import social
    for i in social.info_all():
        record_status(conn, i)
    for i in PENDING:
        record_status(conn, i)

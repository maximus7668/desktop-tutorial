"""Datos FICTICIOS para pruebas (dominios example.*). No son investigación real."""

EST_GOOD = {"demand": 4, "willingness_to_pay": 4, "competition_intensity": 2, "build_cost_eur": 20,
            "time_to_first_sale_days": 14, "legal_risk": 1, "fit": 4}
EST_WEAK = {"demand": 3, "willingness_to_pay": 2, "competition_intensity": 4, "build_cost_eur": 400,
            "time_to_first_sale_days": 90, "legal_risk": 1, "fit": 2}


def research_fixture(run_id: str = "ficticia-1") -> dict:
    return {
        "run_id": run_id,
        "method": "Datos ficticios de prueba",
        "opportunities": [
            {
                "title": "Kit de plantillas de presupuestos para reformas",
                "description": "Pequeñas empresas de reformas pierden tiempo haciendo presupuestos a mano. "
                               "Un kit de plantillas en hoja de cálculo ahorra horas cada semana. "
                               "Se entrega como descarga inmediata.",
                "segment": "Empresas de reformas",
                "product_idea": "Plantillas de presupuesto listas para usar",
                "price_hint_eur": 19,
                "estimates": EST_GOOD,
                "evidence": [
                    {"url": "https://foro.example.com/hilo/1", "title": "Hilo: cómo hacéis presupuestos",
                     "excerpt": "Varios usuarios dicen que tardan horas en cada presupuesto.", "kind": "pain"},
                    {"url": "https://tienda.example.org/plantillas", "title": "Plantillas a 25 €",
                     "excerpt": "Un competidor vende plantillas similares a 25 euros.", "kind": "price"},
                    {"url": "https://blog.example.net/encuesta", "title": "Encuesta del sector",
                     "excerpt": "El 60 % de los encuestados busca herramientas sencillas para presupuestar.",
                     "kind": "demand"},
                ],
            },
            {
                "title": "Curso de cerámica online",
                "description": "Curso en vídeo de cerámica para principiantes. Requiere grabación profesional. "
                               "Mucha competencia gratuita.",
                "segment": "Aficionados",
                "product_idea": "Curso en vídeo",
                "price_hint_eur": 49,
                "estimates": EST_WEAK,
                "evidence": [
                    {"url": "https://videos.example.com/ceramica", "title": "Vídeos gratis",
                     "excerpt": "Hay cientos de vídeos gratuitos sobre cerámica básica.", "kind": "competition"},
                ],
            },
        ],
    }

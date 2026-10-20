# Instrucciones para la investigación semanal (sesión de Claude Code programada)

Este fichero lo lee la sesión programada de Claude Code que hace de investigador con la suscripción del
propietario. El propietario puede editarlo para cambiar el foco.

## Objetivo

Encontrar **entre 2 y 4 oportunidades nuevas** de productos digitales que:
- una sola persona pueda crear **sin gastar dinero** (el capital actual puede ser 0 €);
- se puedan probar con una página de lista de espera y tráfico orgánico;
- tengan clientes en España (prioridad) o en países hispanohablantes;
- encajen con el propietario: conoce pequeños negocios locales (peluquerías, talleres, clínicas, comercios)
  y la IA aplicada a ellos.

Evitar: productos que requieran licencias o titulación, asesoramiento financiero, sanitario o jurídico
personalizado, contenido para adultos, apuestas, criptomonedas, o cualquier cosa que prometa ingresos.

## Método

1. Lee los JSON que ya hay en `investigaciones/entrada/` y **no repitas** oportunidades ni títulos.
2. Busca en la web señales reales de:
   - demanda o problema (foros, preguntas, noticias, datos oficiales: INE, Seguridad Social, AEAT…);
   - disposición a pagar (productos parecidos con precio, en euros si es posible);
   - competencia, sobre todo gratuita.
3. Cada evidencia necesita una **URL real que hayas visto en los resultados**. No inventes URLs, cifras ni citas.
   Si solo viste el resumen del resultado y no la página, pon `"reliability": "medium"` como máximo.
4. Las `estimates` son tu juicio (0-5); sé escéptico: si hay alternativas gratuitas buenas, la disposición
   a pagar no debería pasar de 2.
5. `benefits` es texto **público** para la página: beneficios concretos para el cliente, sin promesas de
   ingresos, sin cifras inventadas, sin superlativos («el mejor», «garantizado»).

## Formato

Fichero `investigaciones/entrada/AAAA-MM-DD.json` (fecha de hoy) con este esquema, igual que
`investigaciones/entrada/2026-10-20.json`:

```json
{
  "run_id": "semanal-AAAA-MM-DD",
  "method": "Qué buscaste y cómo (consultas, límites)",
  "opportunities": [{
    "title": "...", "description": "análisis interno (no se publica)", "segment": "...",
    "product_idea": "...", "price_hint_eur": 15,
    "benefits": ["beneficio 1", "beneficio 2", "beneficio 3"],
    "estimates": {"demand": 0, "willingness_to_pay": 0, "competition_intensity": 0,
                  "build_cost_eur": 0, "time_to_first_sale_days": 30, "legal_risk": 0, "fit": 0},
    "evidence": [{"url": "https://...", "title": "...", "publisher": "...", "retrieved_at": "AAAA-MM-DD",
                  "excerpt": "resumen fiel", "kind": "demand|willingness_to_pay|competition|price|pain|regulation|other",
                  "reliability": "high|medium|low"}]
  }]
}
```

## Antes de subirlo

```bash
cd negocio-autonomo
pip install -q -r requirements.txt
APP_SKIP_DOTENV=1 DATABASE_PATH=/tmp/validacion.db python -m app.cli validate-research investigaciones/entrada/AAAA-MM-DD.json
```

Debe decir «Válido». Después: commit solo de ese fichero y push a la rama `claude/negocio-autonomo-mvp`.
No toques código ni otros ficheros. No incluyas datos personales de nadie.

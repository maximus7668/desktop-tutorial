# Ejemplo de investigación de mercado (real, 20/10/2026)

Datos de entrada: [`examples/investigacion_2026-10-20.json`](../examples/investigacion_2026-10-20.json).
Método: 7 búsquedas web hechas en esta sesión. Los extractos resumen lo que mostraban los resultados de
búsqueda; no se leyeron todas las páginas completas. **Las puntuaciones salen de estimaciones mías
(data_kind = estimate), no de mediciones.** Nada de esto valida ninguna idea: solo decide qué probar primero.

## Contexto de mercado (hechos con fuente)

- Unos **3,47 millones de autónomos** en el RETA en julio de 2026 (+1,7 % interanual) — [Bolsamanía / Europa Press](https://www.bolsamania.com/noticias/mercados/economiaparo--uatae-destaca-afiliacion-practicamente-intacta-de-los-autonomos-en-julio-pese-a-perder-103-afiliados--23181463.html).
- **21,1 %** de las empresas de 10+ empleados usó IA en el primer trimestre de 2025 (+8,7 puntos), según el INE — [Bolsamanía](https://www.bolsamania.com/noticias/empresas/economia--el-211-de-empresas-en-espana-de-10-o-mas-empleados-uso-la-ia-en-el-primer-trimestre-del-ano-segun-el-ine--21080387.html). No cubre microempresas.
- **Verifactu aplazado** (Real Decreto-ley 15/2025): sociedades desde el 1/1/2027, resto de obligados desde el 1/7/2027 — [Quipu](https://getquipu.com/blog/verifactu-se-retrasa/), [Genbeta](https://www.genbeta.com/actualidad/gobierno-retrasa-pesadilla-para-empresas-autonomos-verifactu-no-sera-obligatorio-2027/amp). Pendiente de contrastar con el BOE.
- Tarifas de Etsy para vendedores en España: 0,20 $ por anuncio, 6,5 % por transacción, procesamiento ~3 % + fijo y una tarifa regulatoria que subió en junio de 2026 (según guías de terceros, p. ej. [beancount.io](https://beancount.io/es/blog/2026/07/09/etsy-2026-fee-hike-ai-disclosure-rules-handmade-sellers-guide)).

## Oportunidades comparadas

| # | Oportunidad | Puntos | Lo bueno | Lo malo |
|---|---|---|---|---|
| 2 | Instrucciones de IA en español por sector para pequeños negocios | **60** | Adopción de IA creciendo (dato INE); encaja con la experiencia del propietario (DEIKA) | Mucha oferta barata (15.000 instrucciones a 19,99 € en [Gumroad](https://menteprompt.gumroad.com/l/15kprompts)); valor dudoso de packs genéricos ([reseña](https://www.lilachbullock.com/ai-prompt-packs-worth-buying/)) |
| 1 | Plantillas de presupuesto para reformas | 58 | Coste de creación ~0 €; dolor plausible | Competencia gratuita de proveedores de software ([Quipu](https://getquipu.com/blog/plantillas-de-presupuesto-para-reforma/), [STEL Order](https://www.stelorder.com/plantillas/presupuesto-obras-reformas)); la única señal de pago es una plantilla para LATAM con fiabilidad baja |
| 4 | Kit de comunicación Verifactu para gestorías | 58 | Fecha límite real crea urgencia; comprador profesional (B2B) | Ya hay plantillas gratis ([Copilot Gestoría](https://copilotgestoria.com/blog/verifactu-aplazado-2027-fechas-oficiales-comunicar-clientes-gestorias)); riesgo legal si el contenido queda desactualizado |
| 3 | Plantilla de citas para peluquerías | 45 | Barata de crear | Apps gratuitas y proveedores que desaconsejan Excel ([Booksy](https://biz.booksy.com/es-es/blog/por-que-no-debes-utilizar-un-excel-para-peluquerias-y-salones-de-belleza-para-gestionar-las-citas), [Zenoti](https://www.zenoti.com/es/thecheckin/best-hair-salon-scheduling-apps-2026)) |

## Conclusión del sistema

- El director propone un experimento con la **#2** (única con fuentes de demanda y de precio fiables) porque
  supera el umbral de 55 puntos. Es una mejora pequeña frente a las demás: la diferencia está dentro del
  margen de error de unas estimaciones.
- La **#3** se descarta: la evidencia apunta a que el cliente ya tiene alternativas gratuitas mejores.
- Señal de alerta común: en las cuatro hay **alternativas gratuitas**. Por eso el primer experimento no busca
  visitas sino registros con el precio visible, y la validación de verdad exigirá compras reales.
- Siguiente investigación recomendada (barata): 5-10 conversaciones con dueños de pequeños negocios o
  gestorías y búsqueda de volumen de palabras clave. Ninguna requiere gastar dinero.

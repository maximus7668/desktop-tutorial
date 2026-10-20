# Costes estimados

Todo son **estimaciones** a 20/10/2026; revisa precios vigentes antes de contratar nada. Ningún coste se
contrata automáticamente.

## Fijos (mensuales)

| Concepto | Mínimo | Habitual | Notas |
|---|---|---|---|
| Servidor | 0 € (equipo propio) | 4-6 €/mes (VPS pequeño) | 1 vCPU / 1-2 GB basta para SQLite + FastAPI |
| Dominio | ~1 €/mes | 1-2 €/mes | ~10-15 €/año |
| HTTPS | 0 € | 0 € | Let's Encrypt (Caddy) o Cloudflare |
| Copia externa | 0 € | 0-2 €/mes | Almacenamiento con capa gratuita |
| Email transaccional | 0 € | 0-10 €/mes | Muchos proveedores tienen capa gratuita |
| Stripe | 0 € | 0 € | Sin cuota; solo comisión por venta |
| **Total fijo** | **~1 €/mes** | **~6-15 €/mes** | |

Además: posible cuota de autónomo y asesoría si el negocio factura (depende de tu situación: consúltalo).

## Variables

| Concepto | Cómo se calcula | Ejemplo |
|---|---|---|
| Modelo (Claude Opus 5.5) | 4 $/M tokens de entrada, 20 $/M de salida (precio de lista según la documentación vigente) | Una investigación con búsqueda (~30k tokens de entrada, 8k de salida) ≈ 0,12 $ + 0,16 $ = 0,28 $ |
| Búsqueda web del modelo | ~10 $ / 1.000 búsquedas (comprobar precio) | 5 búsquedas ≈ 0,05 $ |
| Investigación completa | Suma de lo anterior | **≈ 0,30-0,60 € por ejecución** (antes de llamar se reservan ~0,45 €). Con el sobre de 10 €/mes caben ~20-30 |
| Stripe (tarjetas UE) | Comisión por transacción (consultar tarifa vigente de Stripe España) | Restar al precio al calcular margen |
| Etsy (si se usa) | 0,20 $/anuncio + 6,5 % transacción + procesamiento + tarifa regulatoria (subió en junio 2026, según guías de terceros) | Pedido de 30 € ≈ 3,7 € en tarifas |
| Anuncios | Lo que apruebes | Por defecto 0 €: los experimentos empiezan con tráfico orgánico |

## Protección de los 500 €

- 100 € de suelo intocable: el sistema solo puede comprometer 400 €.
- Máximo 20 € al día y 50 € por gasto (este segundo límite solo actúa si subes el diario); cambiables solo por ti.
- Cada experimento tiene un tope (≤ 30 € o el 10 % de lo disponible) fijado antes de empezar.
- Coste de la ejecución de prueba de este MVP: **0 €** (sin llamadas a APIs de pago).

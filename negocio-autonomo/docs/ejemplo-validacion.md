# Ejemplo de creación y validación de un producto (ejecución real del sistema, tráfico simulado)

Generado: 2026-10-20T06:16:25+00:00 · entorno: test · BD: data/demo.db

## 1. Investigación importada

Oportunidades creadas: [1, 2, 3, 4] (fuentes reales, ver `examples/investigacion_2026-10-20.json`).

## 2. Evaluación y decisión del director

| # | Oportunidad | Puntuación | Fuentes indep. | Avisos |
|---|---|---|---|---|
| 2 | Pack de instrucciones de IA en español para pequeños negocios | 60.0 | 3 | — |
| 1 | Plantillas de presupuesto para pequeñas empresas de reformas | 58.0 | 3 | sin evidencia de precio/pago: disposición a pagar limitada a 2/5 |
| 4 | Kit para explicar Verifactu a los clientes de una gestoría | 58.0 | 3 | sin evidencia de precio/pago: disposición a pagar limitada a 2/5 |
| 3 | Plantilla de hoja de cálculo para gestionar citas de peluquerías | 45.0 | 3 | sin evidencia de demanda: demanda limitada a 2/5; sin evidencia de precio/pago: disposición a pagar limitada a 2/5 |

Acciones del director: ['evaluadas 4 oportunidades', 'propuesto experimento #1 para «Pack de instrucciones de IA en español para pequeños negocios» (pendiente de aprobación)']

## 3. Experimento propuesto (pendiente de aprobación)

> Experimento #1 sobre «Pack de instrucciones de IA en español para pequeños negocios»: signup_rate ≥ 8.0, mín. 100 visitas, 14 días, presupuesto máx. 0.00 €

- Hipótesis: Al menos un 8% de los visitantes de 'Pequeños negocios locales en España' dejará su email para 'Guía de 40 instrucciones de IA por sector con ejemplos de uso, en español' sabiendo que costará 15.00 €.
- Diseño: Smoke test: página de presentación con precio previsto 15.00 € y lista de espera (sin cobro). Tráfico orgánico. Resultado máximo posible: 'interés sin validar'; para validar hará falta una segunda prueba con pago real.
- Éxito si: signup_rate ≥ 8.0 con ≥ 100 visitantes en 14 días
- Presupuesto máximo: 0.00 € (sin gasto previsto: tráfico orgánico)
- Criterios bloqueados: 2026-10-20T06:16:25+00:00

## 4. Página generada y validada técnicamente

Producto #1 «Pack de instrucciones de IA en español para pequeños negocios» → estado `tested`.

| Comprobación | Resultado |
|---|---|
| titulo | OK |
| encabezado_h1 | OK |
| precio_con_iva | OK |
| enlace_privacidad | OK |
| enlace_aviso_legal | OK |
| llamada_a_la_accion | OK |
| consentimiento_obligatorio | OK |
| sin_plantilla_sin_rellenar | OK |
| sin_scripts | OK |
| tamano_razonable | OK |
| titular_configurado | OK |

HTML guardado en `examples/landing_ejemplo.html`.

## 5. Publicación

Primer intento bloqueado: _Antes de publicar confirma: owner_identity, privacy_policy, commercial_comms, ip_rights_

Tras confirmar el checklist de publicación (solo en demo), la página se publica y el experimento empieza.

## 6. Medición y veredicto

- Datos **reales**: {'visits': 0, 'unique_visitors': 0, 'signups': 0, 'checkout_clicks': 0, 'purchases': 0, 'inquiries': 0, 'signup_rate': 0.0}
- Datos **simulados** (no cuentan): {'visits': 140, 'unique_visitors': 140, 'signups': 21, 'checkout_clicks': 0, 'purchases': 1, 'inquiries': 0, 'signup_rate': 15.0}
- Veredicto: **datos_insuficientes** → decisión **modify**
- No se alcanzó el tráfico mínimo: el resultado no permite concluir. Cambiar canal o mensaje. (Los datos simulados se muestran aparte y no cuentan para el veredicto.)

## 7. Finanzas tras la demo

- Ingresos reales: 0.00 €
- Ingresos simulados (no son ingresos): 15.00 €
- Disponible: 0.00 € de 0.00 €

## 8. Qué haría falta para validar de verdad

1. Completar el checklist legal y desplegar en un dominio real (APP_ENV=production).
2. Llevar tráfico orgánico real (≥ 100 visitantes únicos).
3. Si hay interés, activar cobros (checklist fiscal + Stripe) y repetir con compra real: solo eso valida.

# Acciones que siguen requiriendo aprobación humana

Ningún modo de operación elimina estas aprobaciones. Las del bloque «dinero» están fijadas en el código
(`permissions.py`: las acciones financieras nunca pasan de `approval`).

## Dinero
- Cualquier gasto en anuncios (`ads.spend`), herramientas o servicios (`service.purchase`).
- Gasto de API por encima del sobre mensual preautorizado (`api_envelope_month_cents`).
- Activar cobros reales (`commerce_authorized=on`), solo con el checklist legal/fiscal completo.
- Asignar el enlace de pago de un producto.
- Reembolsos (`payments.refund`): se hacen en Stripe; el sistema solo registra el webhook.
- Aportar capital (panel → Finanzas, o `add-capital`), cambiar el % de suelo, el límite diario o el máximo por gasto.

## Publicación y comunicación
- Empezar un experimento (fija criterios de éxito y presupuesto, que después no se pueden cambiar).
- Publicar una página (modos 1 y 2; en modo 3, según la tabla de permisos).
- Enviar emails (`email.send`).
- Responder consultas sin respuesta aprobada o que parezcan manipulación (se escalan).

## Control del sistema
- Cambiar permisos de cualquier agente (nadie puede cambiar los suyos).
- Cambiar el modo de operación.
- Quitar la parada de emergencia (activarla puede cualquiera).
- Pausar/reanudar la cola o la programación.
- Confirmar cada requisito legal y fiscal.

## Fuera del sistema (siempre manual)
- Alta en Hacienda / Seguridad Social, IVA, facturación: decisión del propietario con su asesor.
- Crear cuentas de pago, anuncios, dominios o servicios de pago.
- Ejecutar campañas publicitarias: el sistema solo prepara el borrador y reserva el presupuesto aprobado.

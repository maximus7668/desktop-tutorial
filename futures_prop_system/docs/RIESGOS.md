# Advertencias sobre riesgos, overfitting y validación continua

**Este software es una herramienta de investigación y ejecución. No es
asesoramiento financiero ni garantiza beneficios.** El trading de futuros con
apalancamiento puede producir pérdidas rápidas y superiores a lo esperado.

## 1. No hay ventaja demostrada

* Los agentes implementan ideas conocidas (momentum, reversión, subasta, flujo).
  **Ninguna tiene ventaja garantizada** en un mercado concreto ni en el futuro.
* El generador sintético incluido sirve para probar la **mecánica** (reglas,
  sizing, fills, rollover). Sus resultados no dicen nada sobre rentabilidad.
  En el backtest sintético de ejemplo el sistema **pierde dinero** (en
  sintético es lo esperado) mientras respeta todas las reglas: eso es
  exactamente lo que valida.

## 2. Overfitting — el riesgo nº 1

* Cada configuración que pruebas aumenta la probabilidad de encontrar un
  resultado bonito por azar. Con 100 pruebas, un Sharpe anual de ~2 en un año
  de datos puede ser **puro ruido**.
* Mitigaciones incluidas: walk-forward con embargo, selección por meseta, PBO
  (CSCV), Deflated Sharpe Ratio, Minimum Track Record Length, hold-out final y
  Monte Carlo/stress. **Úsalas con el nº real de pruebas**, incluidas las que
  "no cuentan".
* Señales de alarma: profit factor > 2.5 in-sample, curvas demasiado suaves,
  rendimiento concentrado en pocos días u operaciones, sensibilidad extrema a
  un parámetro, degradación OOS > 50 %.

## 3. Riesgos específicos de cuentas de fondeo

* **Trailing drawdown intradía**: el umbral sigue al máximo de equity *no
  realizado*. Un trade que llega a +800 y vuelve a 0 consume 800 de colchón.
  Configura `trailing_mode` exactamente como tu firma.
* **Reglas cambiantes**: las firmas modifican DLL, consistencia, contratos
  máximos, horarios y restricciones de noticias. Revisa sus términos cada mes.
  Un incumplimiento por regla desactualizada rompe la cuenta igual.
* **Consistencia**: un gran día puede *impedir* el pago o la superación.
  El `daily_profit_lock_usd` existe por eso.
* **Datos de la firma vs. tus datos**: la firma liquida con SU feed y SU
  cálculo; deja margen (`min_trailing_room_usd`, límites internos).

## 4. Riesgos de mercado y ejecución

* **Gaps y límites de precio**: un stop no garantiza el precio (noticias,
  aperturas, límites de exchange). El sizing incluye un buffer de slippage,
  pero un gap extremo puede superarlo. Los stress tests lo cuantifican.
* **Liquidez**: fuera de RTH y en contratos diferidos el spread y el impacto
  crecen. Por defecto sólo se entra en RTH y en el contrato activo.
* **Rollover**: operar el contrato equivocado o cerca de vencimiento/first
  notice puede implicar entrega física (CL, GC, NG, ZN). El sistema bloquea
  entradas el día previo al roll y cierra/rola posiciones; verifica tu broker.
* **Márgenes**: los exchanges los suben sin aviso en volatilidad; los
  valores del YAML son orientativos.
* **Tecnología**: desconexiones, órdenes duplicadas, relojes desincronizados,
  fallos del broker. Usa brackets nativos del servidor, reconciliación y kill
  switch; nunca dejes posiciones sin stop.

## 5. Riesgos de modelo

* Los modelos de régimen (incluido el HMM) **cambian de comportamiento** con
  el mercado; se reajustan sólo con datos pasados y deben revalidarse.
* El order flow con delta *estimado* (sin bid/ask) es una aproximación pobre;
  la confianza se reduce a la mitad automáticamente, pero lo ideal son datos
  de tick reales.
* La policy RL puede aprender artefactos del simulador. Por eso sólo se le
  permite **reducir** tamaño.

## 6. Validación continua obligatoria

1. Revalidación walk-forward trimestral y tras cualquier cambio.
2. Monitorizar drift de rendimiento frente a la distribución Monte Carlo.
3. Volver a paper ante: 3 semanas fuera del rango esperado, cambios de
   reglas de la firma, cambios estructurales del mercado o del broker.
4. Mantener el log de decisiones (JSONL) para auditoría y replay.

**Opera sólo capital cuya pérdida puedas asumir.**

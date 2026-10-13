# Guía de validación, entrenamiento y paso seguro de paper a live

> Regla de oro: **ninguna fase se salta**. Cada fase tiene criterios de salida
> cuantitativos fijados *antes* de ver los resultados. Si una fase falla, se
> vuelve a la anterior; no se "ajusta un poco" y se repite la misma fase.

## Fase 0 — Datos y contratos (1-2 semanas)

1. Obtén **barras por contrato** (no sólo la continua del proveedor) con
   volumen y, si es posible, open interest y volumen bid/ask (para order flow
   real). Mínimo recomendable: 2-3 años de barras de 1-5 min.
2. Colócalas en `data/{ROOT}/{SYMBOL}.csv` (`ts` ISO8601 UTC, `open, high, low,
   close, volume[, bid_volume, ask_volume, open_interest]`). `validate_bars`
   rechaza duplicados, OHLC incoherente y volumen negativo.
3. Verifica la librería `config/instruments.yaml` contra la web del exchange:
   multiplicador, tick, **márgenes actuales**, meses listados, reglas de
   vencimiento y *first notice day*. Añade los festivos del exchange a
   `ContractCalendar(holidays=...)`.
4. Compara las fechas de roll calculadas con las de tu proveedor/broker y
   decide método (calendario vs. volumen/OI). Revisa visualmente la serie
   continua alrededor de cada roll (no debe haber saltos).
5. Carga el calendario de noticias (`data/news.csv`) con hora exacta.

**Criterio de salida**: `pytest` en verde; cero gaps de roll visibles; fechas
de vencimiento iguales a las oficiales para 2 años de contratos.

## Fase 1 — Investigación in-sample (acotada)

* Reserva **desde el principio** el último 25-30 % del histórico como
  *hold-out final*. No se mira hasta la Fase 3.
* Explora agentes y parámetros con `scripts/run_backtest.py` sobre el 70 %
  restante. **Registra cada configuración probada** (cuenta para el DSR).
* Prefiere pocos parámetros, rejillas gruesas y lógica con explicación causal
  de mercado (subasta, flujo, estacionalidad), no "lo que funcionó".

## Fase 2 — Walk-forward (fuera de muestra)

```
python scripts/run_walk_forward.py --data-dir data --days 500 --train-days 120 --test-days 40
```

* Embargo ≥ 1 día entre train y test; ventanas móviles (no anclas) para
  detectar degradación.
* Selección por **meseta** (mediana del vecindario), nunca por el pico.
* Criterios de salida (todos):
  - PnL OOS agregado > 0 **después** de costes con slippage ×2.
  - Ninguna ventana OOS rompe la cuenta; utilización máxima del DD < 60 %.
  - Profit factor OOS > 1.2 con ≥ 100 operaciones OOS.
  - **PBO < 0.3** y **Deflated Sharpe Ratio > 0.9** con el nº real de pruebas.
  - Monte Carlo sobre días OOS: **P(bust) < 10 %**, P(pass) creciente en 60 días.
  - Stress tests: P(bust) < 25 % con slippage ×3 y con gaps de 400-500 USD.

## Fase 3 — Hold-out final (una sola vez)

Ejecuta la configuración congelada sobre el 25-30 % reservado. Si no cumple
los mismos criterios de la Fase 2, **se descarta** (no se re-optimiza sobre el
hold-out: quedaría contaminado).

## Fase 4 — Entrenamiento RL (opcional)

1. Genera oportunidades **sólo OOS** (de las ventanas walk-forward).
2. `python scripts/train_rl.py` entrena en el 70 % cronológico inicial.
3. Adopta la policy RL sólo si en el 30 % final mejora P(pass) **y** reduce
   P(bust) frente a la heurística en Monte Carlo. Si no, quédate con la
   heurística: es transparente y auditable.
4. Aun adoptada, la policy RL sólo puede **reducir** tamaño (`RLSizingPolicy`).

## Fase 5 — Paper trading (mínimo 4-6 semanas, ≥ 60 operaciones)

```
python scripts/run_paper.py --mode paper --data-dir <feed>
```

* Usa el feed real de barras cerradas y el MISMO `config` que en la Fase 3.
* Compara a diario paper vs. backtest del mismo periodo: nº de señales,
  slippage, PnL por operación. Divergencias > 30 % = bug o supuestos irreales.
* Criterios de salida: PnL dentro del intervalo esperado por Monte Carlo,
  cero incidencias de reglas, slippage medio ≤ el modelado.

## Fase 6 — Live con propuesta + confirmación (2-4 semanas)

* `execution.mode: live_proposal`. Cada operación requiere confirmación humana
  y **se re-evalúa** con el RiskEngine al confirmarla.
* Implementa `LiveBrokerAdapter` con **brackets nativos del servidor** (el
  stop debe existir aunque tu proceso muera), reconciliación de posiciones al
  arrancar y cada minuto, y heartbeat del feed.
* Empieza con **1 micro** fijo: `risk.max_contracts_per_root: {MES: 1, ...}`.
* Checklist diario pre-apertura: calendario de noticias cargado, contrato
  activo correcto (`RolloverManager.status`), márgenes del día, kill switch
  probado, `state.json` y alertas funcionando.

## Fase 7 — Ejecución automática con límites (escalado gradual)

* `execution.mode: live_auto` sólo tras ≥ 40 operaciones en propuesta sin
  incidencias.
* Escala el tamaño **por escalones** (1 → 2 → 3 micros...) cada ≥ 20
  operaciones dentro de lo esperado; nunca tras una racha ganadora "porque va
  bien".
* Mantén `max_orders_per_minute` bajo y el kill switch accesible
  (`LiveRunner.kill`).

## Monitorización continua (siempre)

* **Drift de rendimiento**: si el PnL de las últimas N operaciones cae por
  debajo del percentil 5 de Monte Carlo → volver a paper.
* **Drift de datos/régimen**: distribución de regímenes y de ATR vs.
  entrenamiento; agentes con factor de rendimiento < 0.5 de forma sostenida.
* **Ejecución**: slippage medio, rechazos, latencias.
* Re-validación walk-forward **trimestral** (y tras cualquier cambio de código
  o de reglas de la firma). Los cambios de parámetros pasan otra vez por las
  Fases 2-5.

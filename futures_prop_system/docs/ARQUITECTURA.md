# Arquitectura de `propfut`

Sistema multi-agente de trading **exclusivamente de futuros** para cuentas de
fondeo. Principio rector: **la supervivencia de la cuenta y el cumplimiento de
las reglas tienen prioridad absoluta sobre la rentabilidad.** Todo flujo de
órdenes atraviesa un motor de riesgo con veto absoluto.

## 1. Diagrama

```mermaid
flowchart TB
    subgraph DATA["1 · Futures Data Layer"]
        P[DataProvider<br/>CSV/Parquet/broker] --> V[validate_bars]
        V --> RS[Roll schedule<br/>calendar / volume / OI]
        RS --> CC[Serie continua<br/>back-adjust + raw_*]
        CC --> FE[FeatureEngine causal<br/>ATR, ER, VWAP, delta/CVD,<br/>volume profile, OR, ON,<br/>estacionalidad intradía]
        NEWS[NewsCalendar<br/>+ SentimentProvider]
    end

    subgraph BRAIN["2-4 · Decisión"]
        FE --> RD[Regime Engine<br/>scores + HMM filtrado<br/>+ histéresis]
        FE --> AG[7 agentes especialistas]
        NEWS --> AG
        NEWS --> RD
        RD --> EN[Ensemble dinámico<br/>peso = base × afinidad(régimen)<br/>× rendimiento OOS]
        AG --> EN
        EN --> PO[Policy<br/>heurística / RL<br/>size_fraction ∈ 0..1]
    end

    subgraph RISK["5 · Risk & Compliance Engine (VETO ABSOLUTO)"]
        PO --> RE{RiskEngine.evaluate}
        ACC[AccountState<br/>trailing intradía/EOD/estático,<br/>DLL, consistencia] --> RE
        RE -->|vetada| LOG
        CB[Circuit breakers<br/>cada barra] --> EX
        ACC --> CB
    end

    subgraph EXEC["6 · Execution & Contract Manager"]
        RE -->|aprobada: N contratos| EX[ExecutionManager<br/>bracket OCO obligatorio]
        EX -->|backtest / paper| SB[SimulatedBroker<br/>fills conservadores]
        EX -->|live| LB[LiveBrokerAdapter<br/>brackets nativos del servidor]
        EX --> ROLL[Rollover de posiciones]
        SB --> EX
        LB --> EX
        EX --> ACC
    end

    subgraph MON["7 · Monitoring"]
        LOG[DecisionLogger JSONL] --- AL[AlertManager<br/>log / webhook]
        AL --- DB[Dashboard<br/>state.json + Streamlit]
    end

    subgraph RES["8 · Validation & Research"]
        BT[Backtest event-driven] --> WF[Walk-forward<br/>selección por meseta]
        BT --> MC[Monte Carlo de la evaluación<br/>+ stress tests]
        WF --> OF[PBO · DSR · MinTRL]
    end
```

El mismo `TradingSystem.on_timestamp()` se ejecuta en **backtest, paper y live**:
lo validado es exactamente lo que se ejecuta.

## 2. Ciclo por barra (`propfut/system.py`)

`ts` es la **apertura** de la barra; las decisiones se toman a su **cierre** (`ts + intervalo`).

1. **Inicio de día** de trading (reset 17:00 CT): trailing EOD, reset de contadores.
2. **Rollover**: si cambió el contrato activo y hay posición → `flatten` (por defecto) o `roll`.
3. **Fills** de órdenes pendientes: entradas a la apertura; después stops/targets.
4. **Mark-to-market pesimista**: el máximo de la barra actualiza el HWM *antes* de evaluar la ruptura con el mínimo.
5. **Circuit breakers**: ruptura, kill switch, DLL, pérdida diaria interna, colchón trailing, hora de cierre (con anticipación de una barra), noticias.
6. **Gestión**: breakeven, trailing por ATR (sólo estrecha), time stop, salida por señal opuesta.
7. **Decisión**: régimen → agentes → ensemble → policy → `RiskEngine.evaluate` → bracket.

## 3. Módulos

### 3.1 Futures Data Layer (`contracts/`, `data/`)
| Componente | Función |
|---|---|
| `ContractSpec` | Multiplicador, tick, valor del tick (validado = mult×tick), márgenes, comisiones, equivalencia en minis. **Toda** conversión precio↔USD pasa por aquí. |
| `ContractCalendar` | Último día de negociación por regla de exchange (índices: 3er viernes; FX IMM; CL: 3 d.h. antes del 25 del mes previo; NG; metales con *first notice day*; Treasuries) con festivos explícitos. |
| `determine_roll_schedule` | Roll por calendario, volumen u OI, confirmación de N días, **nunca después** de la fecha de seguridad. |
| `build_continuous` | Back-adjust por diferencia (PnL en USD correcto) o ratio (retornos correctos). Conserva `raw_*` y el contrato de cada barra. |
| `FeatureEngine` | Features **causales** (test automático de no look-ahead): ATR, ER, EMAs, Donchian, Bollinger/Keltner, VWAP, delta real o estimado, CVD, z-scores, estacionalidad por minuto del día, volume profile previo (POC/VAH/VAL), opening range, overnight. |
| `term_structure_features`, `basis_features`, `cot_index` | Contango/backwardation, basis y posicionamiento COT. |
| `NewsCalendar` | Blackouts por impacto; eventos sistémicos (CPI, NFP, FOMC) afectan a todo el universo. |

### 3.2 Regime Detection Engine (`regime/`)
Probabilidades suaves sobre `TREND_UP/DOWN, RANGE, HIGH_VOL, SQUEEZE`
(+ `NEWS_DRIVEN` forzado por calendario). Combina medidas explicables con un HMM
gaussiano de volatilidad **filtrado hacia delante** (ajustado sólo con datos de
entrenamiento) y aplica histéresis. Produce `risk_multiplier` y la distribución
que pondera a los agentes.

### 3.3 Multi-Agent Signal Generation (`agents/`)
| Agente | Lógica | Régimen afín |
|---|---|---|
| `trend` | Breakout Donchian filtrado por ER + continuación en pullback | Tendencia |
| `mean_reversion` | Fade de extensiones (z Bollinger + VWAP) sólo si ER bajo | Rango |
| `volatility` | Squeeze release (rango vs. típico de esa hora) + opening range breakout | Squeeze |
| `order_flow` | Divergencia precio/CVD (absorción) e imbalances agresivos | Todos |
| `auction` | Regla del 80 %, subasta fallida en VAH/VAL, aceptación fuera de value | Rango |
| `macro_news` | Veto pre-evento / blackout; sesgo de sentimiento | — |
| `intermarket` | Reversión del residuo de una relación (ES↔NQ, CL→NG...) si la correlación es estable | Rango |

Cada señal: dirección, confianza, horizonte, stop/target en ATR y explicación.
El **ensemble** pondera `base × afinidad(P(régimen)) × rendimiento`, donde el
rendimiento se mide con señales ya vencidas (sin look-ahead), encogido hacia 1
con poca muestra y acotado en [0.25, 2]. Exige confianza y acuerdo mínimos.

### 3.4 Policy / RL (`policy/`)
* `HeuristicPolicy` (por defecto): convicción → `size_fraction`, ajustada por
  régimen, acuerdo, pérdidas recientes y PnL del día; elige market/limit.
* `PropFirmSizingEnv` (API Gymnasium): el agente RL aprende *selección y tamaño*
  sobre oportunidades **out-of-sample**, con la cuenta simulada bajo las reglas
  de la firma. Recompensa: PnL/R − penalización por aumento de DD, ruptura (−50),
  stop diario, sobreoperación y riesgo con colchón bajo + bonus de consistencia,
  profit factor y objetivo.
* `RLSizingPolicy`: **sólo puede reducir** el tamaño de la heurística. El
  RiskEngine sigue siendo la última palabra.

### 3.5 Risk & Prop Firm Compliance Engine (`risk/`) — crítico
`AccountState` replica las reglas de la firma (trailing intradía/EOD/estático
con *lock*, DLL "pause" o "breach", consistencia, días mínimos).
`RiskEngine.evaluate` aplica, en orden: estado de cuenta → horario/roll/noticias
→ límites diarios → validación de stop y R:R → **sizing en contratos enteros**:

```
riesgo/contrato = |entrada − stop| × multiplicador + (buffer + slippage) × tick_value + 2 × comisión
presupuesto     = min(riesgo_máx_trade,
                      f_dd    × (colchón_trailing − riesgo_abierto − colchón_mínimo),
                      f_daily × (límite_diario_interno + PnL_día − riesgo_abierto))
                  × multiplicador_por_utilización_DD × size_fraction(policy)
contratos       = floor(presupuesto / riesgo/contrato)
```

Después: límites de contratos (en minis, firma e internos), posiciones abiertas,
margen, **riesgo de cartera con correlaciones** `sqrt(wᵀCw)` y **peor caso**
(todos los stops con slippage no pueden romper ningún límite duro).
`check_circuit_breakers` fuerza `FLATTEN`/`HALT` en cada barra.

### 3.6 Execution & Contract Manager (`execution/`)
Bracket obligatorio (entrada + stop + target OCO); parciales sincronizados;
modo propuesta con caducidad y **re-validación al confirmar**; limitador de
órdenes/minuto; detección de slippage anómalo → halt; rollover de posiciones.
`SimulatedBroker` usa supuestos conservadores (stop antes que target en la misma
barra, limit sólo con *trade-through*, participación máxima, gaps al open).

### 3.7 Monitoring (`monitoring/`)
Log JSONL de cada decisión (señales, régimen, checks de riesgo, órdenes, fills),
alertas deduplicadas por umbrales de utilización del drawdown, `state.json`
atómico, render de terminal y app Streamlit.

### 3.8 Validation & Research (`backtest/`)
Backtest event-driven; métricas de prop firm; walk-forward con embargo y
selección por **meseta**; Monte Carlo de la evaluación por días completos
(bootstrap por bloques, respeta trailing intradía); stress tests; PBO (CSCV),
Deflated Sharpe Ratio y Minimum Track Record Length.

## 4. Estructura de carpetas

```
futures_prop_system/
├── config/
│   ├── instruments.yaml          # librería de contratos (ES, MES, NQ, MNQ, YM, RTY, CL, MCL, NG, GC, MGC, SI, 6E, 6J, ZN...)
│   └── account_50k.yaml          # reglas de la firma + límites internos + agentes + ejecución
├── docs/                         # arquitectura, validación/despliegue, riesgos
├── scripts/
│   ├── run_backtest.py           # backtest + Monte Carlo + stress + PSR
│   ├── run_walk_forward.py       # WF + PBO + DSR + MC OOS
│   ├── run_paper.py              # paper / análisis / propuesta sobre replay
│   └── train_rl.py               # PPO sobre oportunidades OOS
├── src/propfut/
│   ├── core/        config.py · sessions.py · types.py
│   ├── contracts/   specs.py · calendar.py · rollover.py
│   ├── data/        providers.py · features.py · volume_profile.py · news.py
│   ├── regime/      detector.py · hmm.py
│   ├── agents/      base.py · technical.py · microstructure.py · macro.py · ensemble.py
│   ├── policy/      base.py · reward.py · rl_env.py
│   ├── risk/        account.py · engine.py
│   ├── execution/   orders.py · broker.py · manager.py
│   ├── backtest/    engine.py · metrics.py · walk_forward.py · monte_carlo.py · overfitting.py
│   ├── monitoring/  logger.py · alerts.py · dashboard.py
│   ├── system.py    # orquestador común a todos los modos
│   └── live.py      # runner paper/live + plantilla de adaptador de broker
└── tests/                        # 80+ tests: reglas, sizing, fills, causalidad, invariantes
```

## 5. Decisiones de diseño clave

* **Micros por defecto**: con 2.000 USD de drawdown, 1 ES con stop de 8 puntos
  arriesga 400 USD (20 % del colchón). Los micros dan la granularidad necesaria.
* **Límites internos más estrictos** que la firma (soft stop 400, flatten 600 vs.
  DLL 1.000; 3 minis vs. 5) para absorber slippage, gaps y errores de modelo.
* **Sin piramidación** y una posición por raíz: menos superficie de error.
* **Sin entradas** los primeros minutos de RTH, cerca del cierre obligatorio,
  en blackout de noticias ni el día previo a un roll.
* **Pesimismo sistemático** en la simulación (orden intrabarra, fills, gaps).

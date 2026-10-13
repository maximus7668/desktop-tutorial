# propfut — sistema multi-agente de trading de futuros para cuentas de fondeo

Sistema en Python 3.11+ orientado **exclusivamente a futuros** (índices,
energía, metales, divisas, tipos) para una cuenta de fondeo de 50.000 USD.
Prioriza la **supervivencia de la cuenta**, el control estricto del drawdown y
la consistencia por encima de la rentabilidad bruta.

* Arquitectura: [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) (diagrama, módulos, estructura)
* Validación y paso a live: [`docs/VALIDACION_Y_DESPLIEGUE.md`](docs/VALIDACION_Y_DESPLIEGUE.md)
* Riesgos y overfitting: [`docs/RIESGOS.md`](docs/RIESGOS.md)
* Configuración de ejemplo: [`config/account_50k.yaml`](config/account_50k.yaml) + [`config/instruments.yaml`](config/instruments.yaml)

## Qué incluye

| Capa | Implementado |
|---|---|
| Datos de futuros | Especificaciones (mult./tick/valor/márgenes), calendarios de vencimiento y *first notice* por exchange, roll por calendario/volumen/OI, serie continua back-adjusted (+ precios reales), features causales: ATR, ER, VWAP, delta/CVD, volume profile (POC/VAH/VAL), opening range, overnight, estacionalidad intradía, basis/contango, índice COT |
| Régimen | Tendencia ↑/↓, rango, alta volatilidad, squeeze, noticias; HMM de volatilidad filtrado causalmente; histéresis |
| Agentes | Tendencia, mean-reversion, volatilidad/ORB, order flow, auction/volume profile, macro/noticias, intermarket; ensemble dinámico por régimen + rendimiento OOS |
| Policy / RL | Policy heurística auditada + entorno Gymnasium con recompensa orientada a prop firm; PPO opcional que **sólo puede reducir** tamaño |
| Riesgo (veto absoluto) | Trailing intradía/EOD/estático con lock, DLL pause/breach, consistencia, sizing en contratos con presupuesto múltiple, tiers por drawdown, límites en minis, margen, riesgo de cartera correlacionado, peor caso, circuit breakers, kill switch, blackouts de noticias, flatten horario |
| Ejecución | Brackets OCO obligatorios, parciales, modo propuesta con re-validación, rate limiter, rollover de posiciones, broker simulado conservador, plantilla de adaptador real |
| Monitorización | Log JSONL de cada decisión, alertas, `state.json`, dashboard terminal/Streamlit |
| Investigación | Backtest event-driven, métricas de prop firm, walk-forward con meseta, Monte Carlo de la evaluación, stress tests, PBO, DSR, MinTRL |

## Instalación y uso

```bash
cd futures_prop_system
pip install -e ".[dev]"            # núcleo: numpy, pandas, pydantic, pyyaml
pip install -e ".[rl,dashboard]"   # opcional: gymnasium/SB3/torch, streamlit

pytest                             # 80+ tests (reglas, sizing, fills, causalidad, invariantes)

python scripts/run_backtest.py                       # demo con datos sintéticos
python scripts/run_backtest.py --data-dir data/ --days 500
python scripts/run_walk_forward.py --data-dir data/ --days 500 --train-days 120 --test-days 40
python scripts/run_paper.py --mode live_proposal     # propuesta + confirmación
streamlit run src/propfut/monitoring/dashboard.py -- logs/state.json
```

Formato de datos reales: `data/{ROOT}/{SYMBOL}.csv` con columnas `ts` (ISO8601
UTC, apertura de barra), `open, high, low, close, volume` y opcionalmente
`bid_volume, ask_volume, open_interest`; `data/news.csv` con `ts, title,
impact, roots`.

## Ejemplo de uso programático

```python
from propfut.core.config import load_config
from propfut.backtest import run_backtest, PropChallengeSimulator, days_from_history

cfg = load_config("config/account_50k.yaml")
res = run_backtest(cfg, market)          # market: raíz -> DataFrame de prepare_market_data
print(res.summary())
mc = PropChallengeSimulator(cfg.account).simulate(days_from_history(res.daily))
print(mc.p_pass, mc.p_bust)
```

## Estado

El núcleo (datos, contratos/rollover, régimen, agentes, ensemble, riesgo,
ejecución simulada, backtest, investigación) está implementado y probado. La
conexión a un broker real es un punto de integración documentado
(`propfut.live.LiveBrokerAdapter`) que debe implementarse y validarse según la
guía antes de arriesgar capital. **Los resultados con datos sintéticos sólo
validan la mecánica, no la rentabilidad.**

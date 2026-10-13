"""Entrenamiento de la policy RL de sizing (PPO, stable-baselines3) sobre oportunidades OOS.

Flujo correcto:
1. Generar oportunidades con walk-forward (nunca in-sample).
2. Entrenar en la primera parte cronológica, validar en la última (nunca vista).
3. Sólo adoptar la policy si mejora P(pass)/P(bust) de Monte Carlo frente a la heurística.
   Aun así, en producción la policy RL sólo puede REDUCIR el tamaño heurístico.

Uso:
    pip install -e ".[rl]"
    python scripts/train_rl.py --days 200 --timesteps 50000
"""

from __future__ import annotations

import argparse

import numpy as np
from common import ROOT, build_market, load

from propfut.backtest.engine import run_backtest
from propfut.policy.base import OBS_DIM, REGIME_ORDER
from propfut.policy.rl_env import Opportunities, PropFirmSizingEnv


def opportunities_from_result(res, cfg) -> Opportunities:  # type: ignore[no-untyped-def]
    obs, r_mult, day = [], [], []
    days = {d: i for i, d in enumerate(sorted({t.entry_ts.date() for t in res.trades}))}
    for t in res.trades:
        sign = 1.0 if t.side.name == "LONG" else -1.0
        regime = [1.0 if t.regime == r.value else 0.0 for r in REGIME_ORDER]
        v = [sign * t.confidence, t.confidence, 1.0, 0.3, 0.4, *regime, 1.0]
        obs.append(np.asarray(v[: OBS_DIM - 5], dtype=np.float32))
        r_mult.append(t.r_multiple)
        day.append(days[t.entry_ts.date()])
    return Opportunities(np.vstack(obs), np.asarray(r_mult), np.asarray(day))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "account_50k.yaml"))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--days", type=int, default=160)
    ap.add_argument("--timesteps", type=int, default=20000)
    ap.add_argument("--out", default=str(ROOT / "models" / "ppo_sizing"))
    args = ap.parse_args()
    cfg = load(args.config)
    market, news = build_market(cfg, args.data_dir, args.days, seed=3)
    res = run_backtest(cfg, market, news=news)
    if len(res.trades) < 30:
        print(f"Sólo {len(res.trades)} operaciones: insuficiente para entrenar RL de forma fiable.")
    opps = opportunities_from_result(res, cfg)
    n = len(opps.r_multiple)
    cut = int(n * 0.7)
    train = Opportunities(opps.obs[:cut], opps.r_multiple[:cut], opps.day[:cut])
    env = PropFirmSizingEnv(train, cfg.account, cfg.risk.max_risk_per_trade_usd, cfg.risk.daily_loss_soft_stop_usd)
    try:
        from stable_baselines3 import PPO  # type: ignore[import-not-found]
    except ImportError:
        print("stable-baselines3/gymnasium no instalados (pip install -e '.[rl]'). "
              "Ejecutando verificación del entorno con política aleatoria:")
        o, _ = env.reset(seed=0)
        rng = np.random.default_rng(0)
        total, done = 0.0, False
        while not done:
            o, r, term, trunc, info = env.step(int(rng.integers(0, 4)))
            total += r
            done = term or trunc
        print(f"  episodio aleatorio: recompensa={total:.2f} equity={info['equity']:.2f}")
        return
    model = PPO("MlpPolicy", env, verbose=1, n_steps=256, batch_size=64, gamma=0.99, seed=0)
    model.learn(total_timesteps=args.timesteps)
    model.save(args.out)
    print(f"Modelo guardado en {args.out}.zip — valida en el 30 % final antes de usarlo "
          f"(policy.kind: rl, policy.model_path: {args.out}.zip)")


if __name__ == "__main__":
    main()

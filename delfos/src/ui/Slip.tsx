import { LEAGUE_BY_ID } from '../data/leagues';
import { fairDecimal } from '../model/odds';
import { useSlip } from '../state';
import { Empty, LeagueLogo } from './common';
import { dateTime, odds2, pct } from './format';
import { Icon } from './icons';
import { featuredPicks, type Scored } from './Forecasts';
import { slipPickFor } from './slipPick';

export function Slip({ scored, compact = false }: { scored: Scored[]; compact?: boolean }) {
  const slip = useSlip();
  const { picks } = slip;
  const prob = picks.reduce((s, p) => s * p.prob, 1);
  const allMarket = picks.length > 0 && picks.every((p) => p.market);
  const marketOdds = allMarket ? picks.reduce((s, p) => s * (p.market as number), 1) : undefined;
  const ev = marketOdds ? prob * marketOdds - 1 : undefined;
  const suggest = () => {
    const best = featuredPicks(scored, 3).filter((x) => x.p.pickProb >= 0.55);
    slip.replace(best.map((x) => slipPickFor(x.m, x.p, x.p.pick)));
  };

  return (
    <div className={`slip ${compact ? 'slip-compact' : ''}`}>
      <div className="slip-head">
        <h2><Icon name="slip" size={20} /> Mi combinada</h2>
        {picks.length > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={slip.clear}><Icon name="trash" size={15} /> Vaciar</button>
        )}
      </div>
      {picks.length === 0 ? (
        <Empty title="Tu combinada está vacía">
          Pulsa <b>Combinada</b> en cualquier partido para sumar su pronóstico y ver la probabilidad conjunta.
        </Empty>
      ) : (
        <>
          <ul className="slip-list">
            {picks.map((p) => {
              const l = LEAGUE_BY_ID[p.leagueId];
              return (
                <li key={p.matchId} className="slip-item">
                  <div className="slip-item-top">
                    {l && (l.logo ? <LeagueLogo league={l} size={16} /> : <span className="tour-badge sm">{l.short}</span>)}
                    <span className="muted small">{dateTime(p.start)}</span>
                    <button type="button" className="icon-btn sm" onClick={() => slip.remove(p.matchId)} aria-label={`Quitar ${p.matchLabel}`}><Icon name="close" size={15} /></button>
                  </div>
                  <div className="slip-match">{p.matchLabel}</div>
                  <div className="slip-pick">
                    <b>{p.label}</b>
                    <span>{pct(p.prob)}</span>
                    <span className="muted">justa {odds2(fairDecimal(p.prob))}{p.market ? ` · mercado ${odds2(p.market)}` : ''}</span>
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="slip-sum">
            <div><span>Probabilidad conjunta</span><b>{pct(prob, prob < 0.1 ? 1 : 0)}</b></div>
            <div><span>Cuota justa</span><b>{odds2(fairDecimal(prob))}</b></div>
            {marketOdds && <div><span>Cuota de mercado</span><b>{odds2(marketOdds)}</b></div>}
            {ev !== undefined && (
              <div className={ev >= 0 ? 'good' : 'bad'}><span>Valor esperado</span><b>{ev >= 0 ? '+' : ''}{Math.round(ev * 100)} %</b></div>
            )}
          </div>
          <p className="muted small">
            Cada selección multiplica el riesgo: con {picks.length} {picks.length === 1 ? 'selección' : 'selecciones'} aciertas {prob >= 0.5 ? 'algo más de la mitad de las veces' : `aproximadamente ${Math.max(1, Math.round(prob * 10))} de cada 10 veces`}.
          </p>
        </>
      )}
      <button type="button" className="btn btn-gold wide" onClick={suggest} disabled={scored.length === 0}>
        <Icon name="wand" size={16} /> Combinada del Oráculo
      </button>
      <p className="muted tiny">Juego responsable +18 · Delfos no acepta apuestas.</p>
    </div>
  );
}

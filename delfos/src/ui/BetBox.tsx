import type { Match } from '../data/types';
import { allBets, MIN_EV, qualifies, recommendBet, valueLevel, type Bet } from '../model/bets';
import { fairDecimal } from '../model/odds';
import type { Prediction } from '../model/predict';
import { useSlip } from '../state';
import { odds2, pct, pickSentence } from './format';
import { Icon } from './icons';
import { slipPickForBet } from './slipPick';

const LEVEL: Record<ReturnType<typeof valueLevel>, string> = { alto: 'Valor alto', medio: 'Valor medio', ajustado: 'Valor ajustado' };

export function BetBox({ m, p }: { m: Match; p: Prediction }) {
  const slip = useSlip();
  const bet = recommendBet(m, p);
  const bets = allBets(m, p);
  const pickProb = p.pickProb;
  const minPick = (1 + MIN_EV) / pickProb;

  return (
    <section className={`panel betbox ${bet ? 'has-bet' : ''}`} aria-labelledby="bet-title">
      <div className="betbox-head">
        <h3 className="panel-title" id="bet-title"><Icon name="spark" size={17} /> Apuesta recomendada</h3>
        {bet && <span className={`vlevel vlevel-${valueLevel(bet)}`}>{LEVEL[valueLevel(bet)]}</span>}
      </div>

      {bet ? (
        <>
          <div className="betbox-main">
            <div className="betbox-what">
              <span className="eyebrow">{bet.market}</span>
              <b className="betbox-label">{bet.label}</b>
            </div>
            <div className="betbox-odds"><small>Cuota</small>{odds2(bet.odds)}</div>
          </div>
          <div className="betbox-grid">
            <Cell label="Probabilidad Delfos" value={pct(bet.prob)} />
            <Cell label="Probabilidad de la cuota" value={pct(bet.implied)} />
            <Cell label="Valor esperado" value={`+${Math.round(bet.ev * 100)} %`} tone="good" />
            <Cell label="Stake sugerido" value={`${bet.stake.toLocaleString('es-ES')} % banca`} />
          </div>
          <p className="muted small">
            De media y a largo plazo, apuestas así devuelven {(1 + bet.ev).toLocaleString('es-ES', { maximumFractionDigits: 2 })} € por cada euro; a corto plazo manda la suerte.
            Sigue habiendo valor mientras la cuota sea de <b>{odds2(bet.minOdds)}</b> o más. Stake: un cuarto de Kelly, máximo 2 %.
          </p>
          <button
            type="button"
            className={`btn ${slip.has(m.id, bet.key) ? 'btn-ghost' : 'btn-gold'}`}
            onClick={() => slip.toggle(slipPickForBet(m, bet))}
          >
            <Icon name={slip.has(m.id, bet.key) ? 'check' : 'plus'} size={16} />
            {slip.has(m.id, bet.key) ? 'En tu combinada' : 'Añadir a la combinada'}
          </button>
        </>
      ) : (
        <div className="betbox-none">
          <p>
            <b>Sin apuesta recomendada.</b>{' '}
            {m.status !== 'pre'
              ? 'El partido ya ha empezado.'
              : !m.odds
                ? 'No hay cuotas de mercado para este partido.'
                : p.quality === 'escasa' || m.seasonType === 1
                  ? 'Hay pocos datos fiables (o es pretemporada): mejor no apostar.'
                  : `Ninguna cuota paga lo suficiente: Delfos pide al menos un +${Math.round(MIN_EV * 100)} % de valor esperado.`}
          </p>
          {m.status === 'pre' && (
            <p className="muted small">
              Para que <b>{pickSentence(m, p.pick).toLowerCase()}</b> ({pct(pickProb)}) tenga valor haría falta una cuota de <b>{odds2(minPick)}</b> o más (justa: {odds2(fairDecimal(pickProb))}).
            </p>
          )}
        </div>
      )}

      {bets.length > 0 && (
        <details className="table-twin">
          <summary>Todas las cuotas ({bets.length})</summary>
          <div className="table-wrap">
            <table className="bets-table">
              <thead>
                <tr><th>Selección</th><th className="num">Cuota</th><th className="num">Delfos</th><th className="num hide-sm">Justa</th><th className="num">Valor</th><th /></tr>
              </thead>
              <tbody>
                {bets.map((b) => <BetRow key={b.key} m={m} b={b} best={bet?.key === b.key} />)}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

function BetRow({ m, b, best }: { m: Match; b: Bet; best: boolean }) {
  const slip = useSlip();
  const on = slip.has(m.id, b.key);
  return (
    <tr className={best ? 'is-best' : ''}>
      <td><span className="muted tiny">{b.market}</span><br />{b.label}</td>
      <td className="num">{odds2(b.odds)}</td>
      <td className="num">{pct(b.prob)}</td>
      <td className="num hide-sm">{odds2(fairDecimal(b.prob))}</td>
      <td className={`num ${qualifies(b) ? 'good' : b.ev < 0 ? 'bad' : ''}`}>{b.ev >= 0 ? '+' : '−'}{Math.abs(Math.round(b.ev * 100))} %</td>
      <td className="num">
        <button type="button" className={`icon-btn sm ${on ? 'is-on' : ''}`} onClick={() => slip.toggle(slipPickForBet(m, b))} aria-pressed={on} aria-label={on ? `Quitar ${b.label}` : `Añadir ${b.label}`}>
          <Icon name={on ? 'check' : 'plus'} size={15} />
        </button>
      </td>
    </tr>
  );
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: 'good' }) {
  return (
    <div className="betbox-cell">
      <small>{label}</small>
      <b className={tone}>{value}</b>
    </div>
  );
}

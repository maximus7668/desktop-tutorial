import type { Match } from '../data/types';
import { hit, type Prediction } from '../model/predict';
import { useSlip } from '../state';
import { ConfidenceBadge, HitMark, ProbRail, StatusPill, TeamLogo } from './common';
import { odds2, outcomeLabel, pct } from './format';
import { americanToDecimal } from '../model/odds';
import { Icon } from './icons';
import { mlKey, slipPickFor } from './slipPick';
import type { Bet } from '../model/bets';

export function MatchCard({ m, p, bet, onOpen }: { m: Match; p: Prediction; bet?: Bet; onOpen: (id: string) => void }) {
  const slip = useSlip();
  const showScore = m.status !== 'pre' && m.home.score !== undefined && m.away.score !== undefined;
  const ok = hit(m, p);
  const inSlip = slip.has(m.id, mlKey(p.pick));
  const tennis = m.sport === 'tennis';
  const pickTeam = p.pick === 'home' ? m.home : p.pick === 'away' ? m.away : undefined;
  const marketOdds = m.odds ? (p.pick === 'home' ? m.odds.home : p.pick === 'away' ? m.odds.away : m.odds.draw) : undefined;

  return (
    <article className={`match ${m.status === 'in' ? 'is-live' : ''}`}>
      <button type="button" className="match-main" onClick={() => onOpen(m.id)} aria-label={`Ver análisis: ${m.home.team.name} contra ${m.away.team.name}`}>
        <div className="match-time">
          <StatusPill m={m} />
          {tennis && m.round && <span className="match-round">{m.round}</span>}
          {!tennis && m.note && <span className="match-round" title={m.note}>{m.note}</span>}
        </div>
        <div className="match-teams">
          {[m.home, m.away].map((s, i) => (
            <div key={i} className={`team-row ${s.winner ? 'is-winner' : ''}`}>
              <TeamLogo team={s.team} size={26} flag={tennis} />
              <span className="team-name">
                {s.team.name}
                {tennis && s.rank ? <small className="team-meta">{s.rank}</small> : null}
                {!tennis && s.record ? <small className="team-meta">{s.record}</small> : null}
              </span>
              {showScore && <span className="team-score">{s.score}</span>}
              {tennis && m.status !== 'pre' && s.linescores && (
                <span className="sets">{s.linescores.map((x, j) => <i key={j}>{x}</i>)}</span>
              )}
            </div>
          ))}
        </div>
        <div className="match-pick">
          <span className="pick-eyebrow">{m.status === 'pre' ? 'Pronóstico' : 'Pronosticado'}</span>
          <span className="pick-what">
            {pickTeam && <TeamLogo team={pickTeam.team} size={18} flag={tennis} />}
            {outcomeLabel(m, p.pick)}
          </span>
          <span className="pick-num">{pct(p.pickProb)}</span>
          <span className="pick-score">{p.score.home}–{p.score.away}</span>
        </div>
      </button>
      <div className="match-foot">
        <ProbRail m={m} p={p} />
        <div className="match-tags">
          {m.status === 'post' ? <HitMark ok={ok} /> : <ConfidenceBadge c={p.confidence} short />}
          {bet && (
            <span className="tag tag-value" title={`Apuesta recomendada: valor esperado +${Math.round(bet.ev * 100)} %`}>
              <Icon name="spark" size={13} /> <span className="tag-text">{bet.label}</span> @{odds2(bet.odds)}
            </span>
          )}
          {marketOdds !== undefined && !bet && m.status === 'pre' && (
            <span className="tag tag-odds" title="Cuota del mercado para el pronóstico">@{odds2(americanToDecimal(marketOdds))}</span>
          )}
          {m.status === 'pre' && (
            <button
              type="button"
              className={`add-btn ${inSlip ? 'is-on' : ''}`}
              onClick={() => slip.toggle(slipPickFor(m, p, p.pick))}
              aria-pressed={inSlip}
              title={inSlip ? 'Quitar de la combinada' : 'Añadir a la combinada'}
            >
              <Icon name={inSlip ? 'check' : 'plus'} size={15} />
              <span>{inSlip ? 'En combinada' : 'Combinada'}</span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

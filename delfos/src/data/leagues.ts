import type { League, SportId } from './types';

const SOCCER_LOGO = (id: number) => ({
  logo: `https://a.espncdn.com/i/leaguelogos/soccer/500/${id}.png`,
  logoDark: `https://a.espncdn.com/i/leaguelogos/soccer/500-dark/${id}.png`,
});
const US_LOGO = (abbr: string) => ({
  logo: `https://a.espncdn.com/i/teamlogos/leagues/500/${abbr}.png`,
  logoDark: `https://a.espncdn.com/i/teamlogos/leagues/500-dark/${abbr}.png`,
});

export const LEAGUES: League[] = [
  { id: 'esp.1', slug: 'soccer/esp.1', sport: 'soccer', name: 'LaLiga', short: 'LaLiga', region: 'España', order: 1, ...SOCCER_LOGO(15) },
  { id: 'eng.1', slug: 'soccer/eng.1', sport: 'soccer', name: 'Premier League', short: 'Premier', region: 'Inglaterra', order: 2, ...SOCCER_LOGO(23) },
  { id: 'uefa.champions', slug: 'soccer/uefa.champions', sport: 'soccer', name: 'Champions League', short: 'Champions', region: 'Europa', order: 3, ...SOCCER_LOGO(2) },
  { id: 'ita.1', slug: 'soccer/ita.1', sport: 'soccer', name: 'Serie A', short: 'Serie A', region: 'Italia', order: 4, ...SOCCER_LOGO(12) },
  { id: 'ger.1', slug: 'soccer/ger.1', sport: 'soccer', name: 'Bundesliga', short: 'Bundesliga', region: 'Alemania', order: 5, ...SOCCER_LOGO(10) },
  { id: 'fra.1', slug: 'soccer/fra.1', sport: 'soccer', name: 'Ligue 1', short: 'Ligue 1', region: 'Francia', order: 6, ...SOCCER_LOGO(9) },
  { id: 'uefa.europa', slug: 'soccer/uefa.europa', sport: 'soccer', name: 'Europa League', short: 'Europa L.', region: 'Europa', order: 7, ...SOCCER_LOGO(2310) },
  { id: 'uefa.europa.conf', slug: 'soccer/uefa.europa.conf', sport: 'soccer', name: 'Conference League', short: 'Conference', region: 'Europa', order: 8, ...SOCCER_LOGO(20296) },
  { id: 'esp.2', slug: 'soccer/esp.2', sport: 'soccer', name: 'LaLiga Hypermotion', short: 'LaLiga 2', region: 'España', order: 9, logo: 'https://a.espncdn.com/i/leaguelogos/soccer/500/107.png' },
  { id: 'por.1', slug: 'soccer/por.1', sport: 'soccer', name: 'Primeira Liga', short: 'Portugal', region: 'Portugal', order: 10, ...SOCCER_LOGO(14) },
  { id: 'ned.1', slug: 'soccer/ned.1', sport: 'soccer', name: 'Eredivisie', short: 'Eredivisie', region: 'Países Bajos', order: 11, ...SOCCER_LOGO(11) },
  { id: 'mex.1', slug: 'soccer/mex.1', sport: 'soccer', name: 'Liga MX', short: 'Liga MX', region: 'México', order: 12, ...SOCCER_LOGO(22) },
  { id: 'arg.1', slug: 'soccer/arg.1', sport: 'soccer', name: 'Liga Profesional', short: 'Argentina', region: 'Argentina', order: 13, ...SOCCER_LOGO(1) },
  { id: 'bra.1', slug: 'soccer/bra.1', sport: 'soccer', name: 'Brasileirão', short: 'Brasil', region: 'Brasil', order: 14, ...SOCCER_LOGO(85) },
  { id: 'conmebol.libertadores', slug: 'soccer/conmebol.libertadores', sport: 'soccer', name: 'Copa Libertadores', short: 'Libertadores', region: 'Sudamérica', order: 15, ...SOCCER_LOGO(58) },
  { id: 'usa.1', slug: 'soccer/usa.1', sport: 'soccer', name: 'MLS', short: 'MLS', region: 'EE. UU.', order: 16, ...SOCCER_LOGO(19) },
  { id: 'uefa.nations', slug: 'soccer/uefa.nations', sport: 'soccer', name: 'Nations League', short: 'Nations L.', region: 'Selecciones', order: 17, ...SOCCER_LOGO(2395) },
  { id: 'nba', slug: 'basketball/nba', sport: 'basketball', name: 'NBA', short: 'NBA', region: 'EE. UU.', order: 20, ...US_LOGO('nba') },
  { id: 'wnba', slug: 'basketball/wnba', sport: 'basketball', name: 'WNBA', short: 'WNBA', region: 'EE. UU.', order: 21, ...US_LOGO('wnba') },
  { id: 'nfl', slug: 'football/nfl', sport: 'football', name: 'NFL', short: 'NFL', region: 'EE. UU.', order: 30, ...US_LOGO('nfl') },
  { id: 'mlb', slug: 'baseball/mlb', sport: 'baseball', name: 'MLB', short: 'MLB', region: 'EE. UU.', order: 40, ...US_LOGO('mlb') },
  { id: 'nhl', slug: 'hockey/nhl', sport: 'hockey', name: 'NHL', short: 'NHL', region: 'EE. UU. y Canadá', order: 50, ...US_LOGO('nhl') },
  { id: 'atp', slug: 'tennis/atp', sport: 'tennis', name: 'ATP', short: 'ATP', region: 'Circuito masculino', order: 60 },
  { id: 'wta', slug: 'tennis/wta', sport: 'tennis', name: 'WTA', short: 'WTA', region: 'Circuito femenino', order: 61 },
  { id: 'f1', slug: 'racing/f1', sport: 'racing', name: 'Fórmula 1', short: 'F1', region: 'Mundial', order: 70, logo: 'https://a.espncdn.com/i/teamlogos/leagues/500/f1.png' },
];

/** Ligas nacionales de fútbol (tienen clasificación y estadísticas de temporada propias). */
export const DOMESTIC_SOCCER = ['esp.1', 'eng.1', 'ita.1', 'ger.1', 'fra.1', 'por.1', 'ned.1', 'bra.1', 'arg.1', 'mex.1', 'usa.1', 'esp.2'];
/** Competiciones entre equipos de ligas distintas. */
export const CROSS_SOCCER = ['uefa.champions', 'uefa.europa', 'uefa.europa.conf', 'conmebol.libertadores', 'uefa.nations'];

export const LEAGUE_BY_ID: Record<string, League> = Object.fromEntries(LEAGUES.map((l) => [l.id, l]));

export interface SportInfo {
  id: SportId;
  name: string;
  short: string;
}

export const SPORTS: SportInfo[] = [
  { id: 'soccer', name: 'Fútbol', short: 'Fútbol' },
  { id: 'basketball', name: 'Baloncesto', short: 'Basket' },
  { id: 'football', name: 'Fútbol americano', short: 'NFL' },
  { id: 'baseball', name: 'Béisbol', short: 'MLB' },
  { id: 'hockey', name: 'Hockey hielo', short: 'NHL' },
  { id: 'tennis', name: 'Tenis', short: 'Tenis' },
  { id: 'racing', name: 'Fórmula 1', short: 'F1' },
];

export const SPORT_BY_ID: Record<SportId, SportInfo> = Object.fromEntries(SPORTS.map((s) => [s.id, s])) as Record<SportId, SportInfo>;

export const leaguesOf = (sport: SportId) => LEAGUES.filter((l) => l.sport === sport);

/** Equipos y colores de la parrilla 2026 de F1 (ESPN no da la relación piloto-equipo). */
export const F1_TEAMS: Record<string, { team: string; color: string }> = {
  RUS: { team: 'Mercedes', color: '#27F4D2' },
  ANT: { team: 'Mercedes', color: '#27F4D2' },
  LEC: { team: 'Ferrari', color: '#E8002D' },
  HAM: { team: 'Ferrari', color: '#E8002D' },
  NOR: { team: 'McLaren', color: '#FF8000' },
  PIA: { team: 'McLaren', color: '#FF8000' },
  VER: { team: 'Red Bull', color: '#3671C6' },
  HAD: { team: 'Red Bull', color: '#3671C6' },
  LAW: { team: 'Racing Bulls', color: '#6692FF' },
  LIN: { team: 'Racing Bulls', color: '#6692FF' },
  GAS: { team: 'Alpine', color: '#FF87BC' },
  COL: { team: 'Alpine', color: '#FF87BC' },
  OCO: { team: 'Haas', color: '#B6BABD' },
  BEA: { team: 'Haas', color: '#B6BABD' },
  HUL: { team: 'Audi', color: '#BB0A30' },
  BOR: { team: 'Audi', color: '#BB0A30' },
  SAI: { team: 'Williams', color: '#64C4FF' },
  ALB: { team: 'Williams', color: '#64C4FF' },
  ALO: { team: 'Aston Martin', color: '#229971' },
  STR: { team: 'Aston Martin', color: '#229971' },
  PER: { team: 'Cadillac', color: '#C8A45A' },
  BOT: { team: 'Cadillac', color: '#C8A45A' },
};

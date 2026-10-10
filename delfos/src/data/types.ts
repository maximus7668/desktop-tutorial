export type SportId = 'soccer' | 'basketball' | 'football' | 'baseball' | 'hockey' | 'tennis' | 'racing';
export type Status = 'pre' | 'in' | 'post';
export type Outcome = 'home' | 'draw' | 'away';

export interface League {
  id: string;
  /** Ruta ESPN, p. ej. "soccer/esp.1" */
  slug: string;
  sport: SportId;
  name: string;
  short: string;
  region: string;
  logo?: string;
  logoDark?: string;
  /** Orden en las listas: menor primero */
  order: number;
}

export interface Team {
  id: string;
  name: string;
  short: string;
  abbr: string;
  logo?: string;
  color?: string;
  alt?: string;
}

/** Estadísticas de un equipo en un partido jugado (fútbol). */
export interface MatchStats {
  corners?: number;
  sot?: number;
  shots?: number;
  fouls?: number;
  possession?: number;
  yellow?: number;
  red?: number;
}

export interface Side {
  team: Team;
  score?: number;
  winner?: boolean;
  /** Últimos resultados, el más reciente al final: "WWDLW" */
  form?: string;
  record?: string;
  /** Tenis: ranking mundial */
  rank?: number;
  /** Tenis: puntos del ranking */
  rankPoints?: number;
  /** Lanzador o portero probable */
  probable?: string;
  /** Sets ganados en tenis o marcadores parciales */
  linescores?: number[];
  /** Estadísticas del partido (solo fútbol, partidos jugados o en juego) */
  stats?: MatchStats;
}

export interface Odds {
  provider: string;
  /** Cuotas americanas */
  home?: number;
  away?: number;
  draw?: number;
  /** Hándicap del local (negativo si es favorito) */
  spread?: number;
  total?: number;
  over?: number;
  under?: number;
  /** Hándicap con sus cuotas (en fútbol suele ser ±0,5) */
  spreadHomeLine?: number;
  spreadHomeOdds?: number;
  spreadAwayLine?: number;
  spreadAwayOdds?: number;
}

export interface Match {
  id: string;
  leagueId: string;
  sport: SportId;
  start: string;
  /** Hora aún sin confirmar (la fecha es orientativa) */
  timeTbd?: boolean;
  status: Status;
  statusDetail: string;
  completed: boolean;
  clock?: string;
  period?: number;
  home: Side;
  away: Side;
  neutral: boolean;
  venue?: string;
  city?: string;
  note?: string;
  round?: string;
  series?: string;
  broadcast?: string;
  odds?: Odds;
  /** 1 pretemporada, 2 regular, 3 playoffs */
  seasonType?: number;
}

export interface TeamStats {
  teamId: string;
  name: string;
  abbr: string;
  logo?: string;
  gp: number;
  w: number;
  d: number;
  l: number;
  otl: number;
  gf: number;
  ga: number;
  pts?: number;
  rank?: number;
  group?: string;
  streak?: string;
  homeRecord?: string;
  awayRecord?: string;
}

export interface LeagueTable {
  leagueId: string;
  season: string;
  current: TeamStats[];
  previous: TeamStats[];
}

export interface RankEntry {
  id: string;
  name: string;
  rank: number;
  points: number;
}

export interface Driver {
  id: string;
  name: string;
  short: string;
  abbr: string;
  flag?: string;
  rank: number;
  points: number;
  /** Puntos por carrera disputada, en orden cronológico */
  perRace: number[];
}

export interface Constructor {
  id: string;
  name: string;
  color?: string;
  rank: number;
  points: number;
}

export interface RaceSession {
  type: string;
  date: string;
  status: Status;
  /** Ids de piloto en orden de clasificación */
  order: string[];
}

export interface Race {
  id: string;
  name: string;
  short: string;
  start: string;
  end: string;
  venue?: string;
  city?: string;
  sessions: RaceSession[];
}

export interface F1Data {
  race?: Race;
  drivers: Driver[];
  constructors: Constructor[];
}

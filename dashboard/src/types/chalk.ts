export interface StatPrediction {
  stat: string;
  p10: number;
  p25: number;
  median: number;   // aliased from p50
  p75: number;
  ceiling: number;  // aliased from p90
  confidence: "high" | "medium" | "low";
}

export interface FantasyScores {
  draftkings: number;
  fanduel: number;
  yahoo: number;
}

export interface InjuryContext {
  player_status: string;
  absent_teammates: string[];
  opportunity_adjustment: number;
}

export interface PlayerPrediction {
  player_id: number;
  player_name: string;
  game_id: string;
  opponent_team: string;
  as_of_ts: string;
  model_version: string;
  predictions: StatPrediction[];
  fantasy_scores: FantasyScores;
  injury_context: InjuryContext;
}

export interface OverUnderLine {
  player_id: number;
  player_name: string;
  stat: string;
  line: number;
  sportsbook: string;
  over_probability: number;
  under_probability: number;
  implied_over_prob: number;
  edge: number;
  confidence: "high" | "medium" | "low";
}

export interface FantasyProjection {
  player_id: number;
  player_name: string;
  game_id: string;
  platform: string;
  fantasy_scores: FantasyScores;
  floor: number;
  ceiling: number;
  mean: number;
  std: number;
  boom_rate: number;
  bust_rate: number;
}

export interface GameSlate {
  game_id: string;
  home_team: string;
  away_team: string;
  as_of_ts: string;
  predicted_total: number;
  home_predictions: PlayerPrediction[];
  away_predictions: PlayerPrediction[];
}

export interface GameSummary {
  game_id: string;
  date: string;
  home_team_id: number;
  away_team_id: number;
  home_team: string;
  away_team: string;
  status: string;
}

export interface TodayGamesResponse {
  date: string;
  games: GameSummary[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  checks: Record<string, string>;
  timestamp: string;
}

export interface PlayerGameLog {
  game_id: string;
  game_date: string;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  to_committed: number;
  fg3m: number;
  min_played: number;
}

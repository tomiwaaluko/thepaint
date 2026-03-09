import type {
  FantasyProjection,
  GameSlate,
  HealthResponse,
  OverUnderLine,
  PlayerGameLog,
  PlayerPrediction,
  TodayGamesResponse,
} from "../types/chalk";

const BASE_URL = import.meta.env.VITE_API_URL || "";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export const chalkApi = {
  getHealth(): Promise<HealthResponse> {
    return fetchJson("/v1/health");
  },

  getTodayGames(): Promise<TodayGamesResponse> {
    return fetchJson("/v1/games/today");
  },

  getPlayerPrediction(
    playerId: number,
    gameId: string
  ): Promise<PlayerPrediction> {
    return fetchJson(
      `/v1/players/${playerId}/predict?game_id=${gameId}`
    );
  },

  getPlayerHistory(
    playerId: number,
    limit = 10
  ): Promise<PlayerGameLog[]> {
    return fetchJson(
      `/v1/players/${playerId}/history?limit=${limit}`
    );
  },

  getGamePredictions(gameId: string): Promise<GameSlate> {
    return fetchJson(`/v1/games/${gameId}/predict`);
  },

  getPlayerProps(
    playerId: number,
    gameId: string
  ): Promise<OverUnderLine[]> {
    return fetchJson(
      `/v1/players/${playerId}/props?game_id=${gameId}`
    );
  },

  getFantasyProjection(
    playerId: number,
    gameId: string,
    platform = "draftkings"
  ): Promise<FantasyProjection> {
    return fetchJson(
      `/v1/players/${playerId}/fantasy?game_id=${gameId}&platform=${platform}`
    );
  },

  getGameFantasy(
    gameId: string,
    platform = "draftkings"
  ): Promise<{ game_id: string; platform: string; projections: FantasyProjection[] }> {
    return fetchJson(
      `/v1/games/${gameId}/fantasy?platform=${platform}`
    );
  },
};

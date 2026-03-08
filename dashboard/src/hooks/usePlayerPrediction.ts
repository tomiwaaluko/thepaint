import { useQuery } from "@tanstack/react-query";
import { chalkApi } from "../api/chalk";

export function usePlayerPrediction(playerId: number, gameId: string) {
  return useQuery({
    queryKey: ["prediction", playerId, gameId],
    queryFn: () => chalkApi.getPlayerPrediction(playerId, gameId),
    refetchInterval: 10 * 60 * 1000,
    staleTime: 5 * 60 * 1000,
    enabled: !!playerId && !!gameId,
  });
}

export function usePlayerProps(playerId: number, gameId: string) {
  return useQuery({
    queryKey: ["props", playerId, gameId],
    queryFn: () => chalkApi.getPlayerProps(playerId, gameId),
    refetchInterval: 3 * 60 * 1000,
    staleTime: 2 * 60 * 1000,
    enabled: !!playerId && !!gameId,
  });
}

export function usePlayerHistory(playerId: number) {
  return useQuery({
    queryKey: ["history", playerId],
    queryFn: () => chalkApi.getPlayerHistory(playerId),
    staleTime: 30 * 60 * 1000,
    enabled: !!playerId,
  });
}

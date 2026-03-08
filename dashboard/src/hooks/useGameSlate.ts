import { useQuery } from "@tanstack/react-query";
import { chalkApi } from "../api/chalk";

export function useGamePredictions(gameId: string) {
  return useQuery({
    queryKey: ["game", gameId],
    queryFn: () => chalkApi.getGamePredictions(gameId),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 3 * 60 * 1000,
    enabled: !!gameId,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => chalkApi.getHealth(),
    refetchInterval: 60 * 1000,
  });
}

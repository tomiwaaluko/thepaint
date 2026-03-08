import { useQuery } from "@tanstack/react-query";
import { chalkApi } from "../api/chalk";

export function useFantasyBoard(gameId: string, platform = "draftkings") {
  return useQuery({
    queryKey: ["fantasy", gameId, platform],
    queryFn: () => chalkApi.getGameFantasy(gameId, platform),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 3 * 60 * 1000,
    enabled: !!gameId,
  });
}

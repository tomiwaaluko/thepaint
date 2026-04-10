import { useQuery } from "@tanstack/react-query";
import { chalkApi } from "../api/chalk";

export function useRecap(date?: string) {
  return useQuery({
    queryKey: ["recap", date],
    queryFn: () => chalkApi.getRecap(date),
    staleTime: 60 * 60 * 1000, // 1 hour — recaps don't change
    refetchOnWindowFocus: false,
  });
}

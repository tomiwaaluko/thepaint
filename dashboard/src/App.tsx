import { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { chalkApi } from "./api/chalk";
import { GameCard } from "./components/SlateView/GameCard";
import { GameDetailView } from "./components/SlateView/GameDetailView";
import { useHealth } from "./hooks/useGameSlate";
import type { OverUnderLine, FantasyProjection } from "./types/chalk";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
      staleTime: 3 * 60 * 1000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}

/* ─── Skeleton Components ─── */

function GameCardSkeleton() {
  return (
    <div className="min-w-[180px] md:min-w-0 shrink-0 md:shrink w-full p-3 rounded-lg border border-navy-600 bg-navy-800 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 bg-navy-600 rounded" />
        <div className="h-4 w-12 bg-navy-600 rounded" />
      </div>
      <div className="h-3 w-20 bg-navy-600 rounded mt-2" />
    </div>
  );
}

function PlayerCardSkeleton() {
  return (
    <div className="bg-navy-800 rounded-lg border border-navy-600 p-4 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="h-4 w-28 bg-navy-600 rounded mb-1" />
          <div className="h-3 w-16 bg-navy-600 rounded" />
        </div>
        <div className="h-5 w-14 bg-navy-600 rounded" />
      </div>
      <div className="space-y-4 mb-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-8 h-3 bg-navy-600 rounded" />
            <div className="flex-1 h-6 bg-navy-600 rounded" />
          </div>
        ))}
      </div>
      <div className="flex gap-3 pt-2 border-t border-navy-600">
        {[1, 2, 3].map((i) => (
          <div key={i} className="text-center">
            <div className="h-2 w-6 bg-navy-600 rounded mx-auto mb-1" />
            <div className="h-4 w-8 bg-navy-600 rounded mx-auto" />
          </div>
        ))}
      </div>
    </div>
  );
}

function ContentSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="h-6 w-40 bg-navy-600 rounded animate-pulse" />
        <div className="h-5 w-28 bg-navy-600 rounded animate-pulse" />
      </div>
      <div className="flex gap-1 mb-4 border-b border-navy-600 pb-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-8 w-20 bg-navy-600 rounded animate-pulse" />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <PlayerCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

/* ─── Main Dashboard ─── */

function Dashboard() {
  const [selectedGameId, setSelectedGameId] = useState<string>("");
  const [props, setProps] = useState<OverUnderLine[]>([]);
  const [fantasy, setFantasy] = useState<FantasyProjection[]>([]);

  const { data: health } = useHealth();

  // 1. Fetch today's game list (lightweight — renders sidebar instantly)
  const { data: todayData, isLoading: gamesLoading } = useQuery({
    queryKey: ["todayGames"],
    queryFn: () => chalkApi.getTodayGames(),
    staleTime: 3 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  const todayGames = todayData?.games ?? [];
  const effectiveGameId =
    selectedGameId || todayGames[0]?.game_id || "";

  // 2. Fetch full predictions for the selected game only
  const { data: selectedGame, isLoading: predictionLoading } = useQuery({
    queryKey: ["game", effectiveGameId],
    queryFn: () => chalkApi.getGamePredictions(effectiveGameId),
    enabled: !!effectiveGameId,
    staleTime: 3 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  // 3. Load props + fantasy after game predictions arrive
  useEffect(() => {
    if (!selectedGame || !effectiveGameId) return;

    let cancelled = false;

    async function loadDetail() {
      const allPlayers = [
        ...selectedGame!.home_predictions,
        ...selectedGame!.away_predictions,
      ];

      const propResults: OverUnderLine[] = [];
      for (const p of allPlayers.slice(0, 10)) {
        if (cancelled) return;
        try {
          const playerProps = await chalkApi.getPlayerProps(
            p.player_id,
            effectiveGameId
          );
          propResults.push(...playerProps);
        } catch {
          // skip
        }
      }
      if (!cancelled) setProps(propResults);

      try {
        const fantasyData = await chalkApi.getGameFantasy(effectiveGameId);
        if (!cancelled) setFantasy(fantasyData.projections);
      } catch {
        if (!cancelled) setFantasy([]);
      }
    }

    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedGame, effectiveGameId]);

  return (
    <div className="min-h-screen bg-navy-900">
      {/* Header — compact on mobile */}
      <header className="border-b border-navy-600 px-4 md:px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-black tracking-tight">
              <span className="text-chalk-orange">CHALK</span>
            </h1>
            <span className="text-xs text-neutral-400 hidden sm:inline">
              NBA Predictions
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <Activity
                size={12}
                className={
                  health?.status === "ok"
                    ? "text-value-green"
                    : "text-fade-red"
                }
              />
              <span className="text-xs text-neutral-400">
                {health?.status === "ok" ? "Live" : "Degraded"}
              </span>
            </div>

            {todayData && (
              <span className="text-xs text-neutral-400 hidden sm:inline">
                {todayData.date}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Game list — horizontal scroll on mobile, sidebar on desktop */}
          <div className="md:w-64 md:shrink-0">
            <h2 className="text-xs text-neutral-400 uppercase font-bold mb-2">
              {todayData ? `Games \u00B7 ${todayData.date}` : "Games"}
            </h2>
            <div className="flex md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
              {gamesLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <GameCardSkeleton key={i} />
                ))
              ) : todayGames.length > 0 ? (
                todayGames.map((g) => (
                  <div
                    key={g.game_id}
                    className="min-w-[180px] md:min-w-0 shrink-0 md:shrink"
                  >
                    <GameCard
                      gameId={g.game_id}
                      homeTeam={g.home_team}
                      awayTeam={g.away_team}
                      selected={g.game_id === effectiveGameId}
                      onClick={() => setSelectedGameId(g.game_id)}
                    />
                  </div>
                ))
              ) : (
                <div className="text-sm text-neutral-400 py-4">
                  No games scheduled.
                </div>
              )}
            </div>
          </div>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            {predictionLoading ? (
              <ContentSkeleton />
            ) : selectedGame ? (
              <GameDetailView
                game={selectedGame}
                props={props}
                fantasyProjections={fantasy}
              />
            ) : effectiveGameId ? (
              <ContentSkeleton />
            ) : (
              <div className="flex items-center justify-center h-64 text-neutral-400">
                {gamesLoading
                  ? "Loading games..."
                  : "No games to display"}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

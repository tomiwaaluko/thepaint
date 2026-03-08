import { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import { chalkApi } from "./api/chalk";
import { GameCard } from "./components/SlateView/GameCard";
import { GameDetailView } from "./components/SlateView/GameDetailView";
import { useHealth } from "./hooks/useGameSlate";
import type { GameSlate, OverUnderLine, FantasyProjection } from "./types/chalk";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, refetchOnWindowFocus: false },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}

// Hardcoded game IDs for demo — in production, would come from a /v1/games/today endpoint
const DEMO_GAME_IDS = ["0022301192", "0022301190", "0022301189"];

function Dashboard() {
  const [games, setGames] = useState<GameSlate[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string>("");
  const [props, setProps] = useState<OverUnderLine[]>([]);
  const [fantasy, setFantasy] = useState<FantasyProjection[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [gameIdInput, setGameIdInput] = useState("");

  const { data: health } = useHealth();

  // Load games on mount
  useEffect(() => {
    loadGames(DEMO_GAME_IDS);
  }, []);

  async function loadGames(gameIds: string[]) {
    setLoading(true);
    const results: GameSlate[] = [];
    for (const gid of gameIds) {
      try {
        const game = await chalkApi.getGamePredictions(gid);
        results.push(game);
      } catch {
        // Game might not exist in DB
      }
    }
    setGames(results);
    if (results.length > 0 && !selectedGameId) {
      setSelectedGameId(results[0].game_id);
    }
    setLoading(false);
    setLastUpdated(new Date());
  }

  async function loadGameDetail(gameId: string) {
    setSelectedGameId(gameId);
    try {
      // Load props for all players in the game
      const game = games.find((g) => g.game_id === gameId);
      if (game) {
        const allPlayers = [
          ...game.home_predictions,
          ...game.away_predictions,
        ];
        const propResults: OverUnderLine[] = [];
        for (const p of allPlayers.slice(0, 10)) {
          try {
            const playerProps = await chalkApi.getPlayerProps(
              p.player_id,
              gameId
            );
            propResults.push(...playerProps);
          } catch {
            // skip
          }
        }
        setProps(propResults);
      }

      // Load fantasy projections
      try {
        const fantasyData = await chalkApi.getGameFantasy(gameId);
        setFantasy(fantasyData.projections);
      } catch {
        setFantasy([]);
      }
    } catch {
      // skip
    }
  }

  useEffect(() => {
    if (selectedGameId) {
      loadGameDetail(selectedGameId);
    }
  }, [selectedGameId]);

  const selectedGame = games.find((g) => g.game_id === selectedGameId);

  return (
    <div className="min-h-screen bg-navy-900">
      {/* Header */}
      <header className="border-b border-navy-600 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-black tracking-tight">
              <span className="text-chalk-orange">CHALK</span>
            </h1>
            <span className="text-xs text-neutral-400">NBA Predictions</span>
          </div>

          <div className="flex items-center gap-4">
            {/* Custom game ID input */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (gameIdInput.trim()) {
                  loadGames([gameIdInput.trim(), ...DEMO_GAME_IDS]);
                  setSelectedGameId(gameIdInput.trim());
                  setGameIdInput("");
                }
              }}
              className="flex items-center gap-1"
            >
              <input
                type="text"
                value={gameIdInput}
                onChange={(e) => setGameIdInput(e.target.value)}
                placeholder="Game ID..."
                className="bg-navy-800 border border-navy-600 rounded px-2 py-1 text-xs text-neutral-200 w-32 placeholder:text-neutral-400 focus:outline-none focus:border-chalk-orange"
              />
              <button
                type="submit"
                className="p-1 text-neutral-400 hover:text-chalk-orange transition-colors cursor-pointer"
              >
                <RefreshCw size={14} />
              </button>
            </form>

            {/* Status */}
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

            <span className="text-xs text-neutral-400">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <RefreshCw size={24} className="text-chalk-orange animate-spin" />
          </div>
        ) : (
          <div className="flex gap-4">
            {/* Sidebar — game list */}
            <div className="w-64 shrink-0 space-y-2">
              <h2 className="text-xs text-neutral-400 uppercase font-bold mb-2">
                Games
              </h2>
              {games.map((g) => (
                <GameCard
                  key={g.game_id}
                  gameId={g.game_id}
                  homeTeam={g.home_team}
                  awayTeam={g.away_team}
                  predictedTotal={g.predicted_total}
                  playerCount={
                    g.home_predictions.length + g.away_predictions.length
                  }
                  selected={g.game_id === selectedGameId}
                  onClick={() => setSelectedGameId(g.game_id)}
                />
              ))}
              {games.length === 0 && (
                <div className="text-sm text-neutral-400 py-4">
                  No games loaded. Enter a game ID above.
                </div>
              )}
            </div>

            {/* Main content */}
            <div className="flex-1 min-w-0">
              {selectedGame ? (
                <GameDetailView
                  game={selectedGame}
                  props={props}
                  fantasyProjections={fantasy}
                />
              ) : (
                <div className="flex items-center justify-center h-64 text-neutral-400">
                  Select a game to view predictions
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;

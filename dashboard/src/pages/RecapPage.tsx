import { useState } from "react";
import { Link } from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ArrowLeft } from "lucide-react";
import { useRecap } from "../hooks/useRecap";
import type {
  RecapResponse,
  RecapGameEntry,
  RecapPlayerEntry,
  RecapStatComparison,
} from "../types/chalk";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 2, refetchOnWindowFocus: false } },
});

function RecapPage() {
  return (
    <QueryClientProvider client={queryClient}>
      <RecapDashboard />
    </QueryClientProvider>
  );
}

const STAT_LABELS: Record<string, string> = {
  pts: "PTS",
  reb: "REB",
  ast: "AST",
  fg3m: "3PM",
  stl: "STL",
  blk: "BLK",
  to_committed: "TO",
};

const STAT_ORDER = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"];

function formatDate(d: Date): string {
  return d.toISOString().split("T")[0];
}

function displayDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function getYesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return formatDate(d);
}

function RecapDashboard() {
  const [selectedDate, setSelectedDate] = useState(getYesterday);
  const { data, isLoading, isError } = useRecap(selectedDate);

  function shiftDate(days: number) {
    const d = new Date(selectedDate + "T12:00:00");
    d.setDate(d.getDate() + days);
    const now = new Date();
    if (d <= now) {
      setSelectedDate(formatDate(d));
    }
  }

  const canGoForward =
    new Date(selectedDate + "T12:00:00") < new Date(getYesterday() + "T12:00:00");

  return (
    <div className="min-h-screen bg-navy-900">
      {/* Header */}
      <header className="border-b border-navy-600 px-4 md:px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="flex items-center gap-2 group">
              <ArrowLeft
                size={16}
                className="text-neutral-400 group-hover:text-chalk-orange transition-colors"
              />
              <h1 className="text-xl font-black tracking-tight">
                <span className="text-chalk-orange">CHALK</span>
              </h1>
            </Link>
            <span className="text-xs text-neutral-400 hidden sm:inline">
              Predictions Recap
            </span>
          </div>

          {/* Date nav */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => shiftDate(-1)}
              className="p-1 rounded hover:bg-navy-700 text-neutral-400 hover:text-neutral-200 transition-colors cursor-pointer"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-sm text-neutral-200 font-medium min-w-[120px] text-center">
              {displayDate(selectedDate)}
            </span>
            <button
              onClick={() => shiftDate(1)}
              disabled={!canGoForward}
              className={`p-1 rounded transition-colors cursor-pointer ${
                canGoForward
                  ? "hover:bg-navy-700 text-neutral-400 hover:text-neutral-200"
                  : "text-navy-600 cursor-not-allowed"
              }`}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-4">
        {isLoading ? (
          <RecapSkeleton />
        ) : isError ? (
          <div className="text-center py-16 text-neutral-400">
            Failed to load recap data. Try again later.
          </div>
        ) : data && data.games.length > 0 ? (
          <>
            <SummaryBar summary={data.summary} />
            <div className="space-y-6 mt-6">
              {data.games.map((game) => (
                <RecapGameCard key={game.game_id} game={game} />
              ))}
            </div>
          </>
        ) : (
          <div className="text-center py-16 text-neutral-400">
            No recap data for {displayDate(selectedDate)}.
            <br />
            <span className="text-xs">
              Predictions and game results must both exist for this date.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Summary Bar ─── */

function SummaryBar({ summary }: { summary: RecapResponse["summary"] }) {
  const hitPct = (summary.hit_rate * 100).toFixed(0);
  const closePct = (summary.close_rate * 100).toFixed(0);
  const missPct = (summary.miss_rate * 100).toFixed(0);

  return (
    <div className="bg-navy-800 rounded-lg border border-navy-600 p-4">
      <div className="flex flex-wrap items-center gap-6">
        {/* Hit rate */}
        <div className="text-center">
          <div className="text-2xl font-bold text-value-green">{hitPct}%</div>
          <div className="text-[10px] text-neutral-400 uppercase">Hit Rate</div>
        </div>

        {/* Grade bar */}
        <div className="flex-1 min-w-[200px]">
          <div className="flex h-3 rounded-full overflow-hidden">
            {summary.hit_rate > 0 && (
              <div
                className="bg-value-green"
                style={{ width: `${hitPct}%` }}
              />
            )}
            {summary.close_rate > 0 && (
              <div
                className="bg-yellow-500"
                style={{ width: `${closePct}%` }}
              />
            )}
            {summary.miss_rate > 0 && (
              <div
                className="bg-fade-red"
                style={{ width: `${missPct}%` }}
              />
            )}
          </div>
          <div className="flex justify-between mt-1 text-[10px] text-neutral-400">
            <span>
              <span className="text-value-green">{hitPct}%</span> hit
            </span>
            <span>
              <span className="text-yellow-400">{closePct}%</span> close
            </span>
            <span>
              <span className="text-fade-red">{missPct}%</span> miss
            </span>
          </div>
        </div>

        {/* Overall MAE */}
        <div className="text-center">
          <div className="text-2xl font-bold text-neutral-200">
            {summary.overall_mae.toFixed(1)}
          </div>
          <div className="text-[10px] text-neutral-400 uppercase">
            Overall MAE
          </div>
        </div>

        {/* Per-stat MAE */}
        <div className="flex flex-wrap gap-2">
          {STAT_ORDER.filter((s) => s in summary.mae_by_stat).map((stat) => (
            <div
              key={stat}
              className="px-2 py-1 rounded bg-navy-700 text-xs"
            >
              <span className="text-neutral-400">
                {STAT_LABELS[stat] ?? stat}
              </span>{" "}
              <span className="text-neutral-200 font-medium">
                {summary.mae_by_stat[stat].toFixed(1)}
              </span>
            </div>
          ))}
        </div>

        {/* Count */}
        <div className="text-center">
          <div className="text-lg font-bold text-neutral-200">
            {summary.total_predictions}
          </div>
          <div className="text-[10px] text-neutral-400 uppercase">
            Predictions
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Game Card ─── */

function RecapGameCard({ game }: { game: RecapGameEntry }) {
  const hitPct = (game.game_hit_rate * 100).toFixed(0);

  return (
    <div className="bg-navy-800 rounded-lg border border-navy-600 overflow-hidden">
      {/* Game header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy-600">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-neutral-200">
            {game.away_team} @ {game.home_team}
          </h3>
          {game.away_score != null && game.home_score != null && (
            <span className="text-sm text-neutral-400">
              {game.away_score} - {game.home_score}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-400">
            MAE {game.game_mae.toFixed(1)}
          </span>
          <GradeBadge value={Number(hitPct)} label={`${hitPct}% hit`} />
        </div>
      </div>

      {/* Player table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-navy-600">
              <th className="text-left px-4 py-2 text-xs text-neutral-400 font-medium uppercase">
                Player
              </th>
              {STAT_ORDER.map((stat) => (
                <th
                  key={stat}
                  className="px-3 py-2 text-xs text-neutral-400 font-medium uppercase text-center"
                >
                  {STAT_LABELS[stat] ?? stat}
                </th>
              ))}
              <th className="px-3 py-2 text-xs text-neutral-400 font-medium uppercase text-center">
                Grade
              </th>
            </tr>
          </thead>
          <tbody>
            {game.players.map((player) => (
              <RecapPlayerRow key={player.player_id} player={player} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Player Row ─── */

function RecapPlayerRow({ player }: { player: RecapPlayerEntry }) {
  const statMap = Object.fromEntries(player.stats.map((s) => [s.stat, s]));

  return (
    <tr className="border-b border-navy-600/50 hover:bg-navy-700/30 transition-colors">
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-neutral-200 font-medium whitespace-nowrap">
            {player.player_name}
          </span>
          <span className="text-[10px] text-neutral-400 uppercase">
            {player.team_abbreviation} · {player.position}
          </span>
        </div>
      </td>
      {STAT_ORDER.map((stat) => {
        const sc = statMap[stat];
        return sc ? (
          <RecapStatCell key={stat} comparison={sc} />
        ) : (
          <td key={stat} className="px-3 py-2.5 text-center text-neutral-400">
            —
          </td>
        );
      })}
      <td className="px-3 py-2.5 text-center">
        <div className="flex items-center justify-center gap-1">
          {player.hit_count > 0 && (
            <span className="text-[10px] font-semibold text-value-green">
              {player.hit_count}H
            </span>
          )}
          {player.close_count > 0 && (
            <span className="text-[10px] font-semibold text-yellow-400">
              {player.close_count}C
            </span>
          )}
          {player.miss_count > 0 && (
            <span className="text-[10px] font-semibold text-fade-red">
              {player.miss_count}M
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

/* ─── Stat Cell ─── */

const GRADE_BG: Record<string, string> = {
  hit: "bg-value-green/10",
  close: "bg-yellow-500/10",
  miss: "bg-fade-red/10",
};

const GRADE_TEXT: Record<string, string> = {
  hit: "text-value-green",
  close: "text-yellow-400",
  miss: "text-fade-red",
};

function RecapStatCell({ comparison }: { comparison: RecapStatComparison }) {
  const { predicted, actual, grade } = comparison;

  return (
    <td className={`px-3 py-2.5 text-center ${GRADE_BG[grade]}`}>
      <div className="flex flex-col items-center">
        <span className={`text-sm font-bold ${GRADE_TEXT[grade]}`}>
          {actual}
        </span>
        <span className="text-[10px] text-neutral-400">
          {predicted.toFixed(1)}
        </span>
      </div>
    </td>
  );
}

/* ─── Grade Badge ─── */

function GradeBadge({ value, label }: { value: number; label: string }) {
  const color =
    value >= 60
      ? "bg-value-green/20 text-value-green"
      : value >= 40
        ? "bg-yellow-500/20 text-yellow-400"
        : "bg-fade-red/20 text-fade-red";

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}>
      {label}
    </span>
  );
}

/* ─── Loading Skeleton ─── */

function RecapSkeleton() {
  return (
    <div className="space-y-6">
      <div className="bg-navy-800 rounded-lg border border-navy-600 p-4 animate-pulse">
        <div className="flex items-center gap-6">
          <div className="h-10 w-16 bg-navy-600 rounded" />
          <div className="flex-1 h-3 bg-navy-600 rounded-full" />
          <div className="h-10 w-16 bg-navy-600 rounded" />
        </div>
      </div>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="bg-navy-800 rounded-lg border border-navy-600 animate-pulse"
        >
          <div className="px-4 py-3 border-b border-navy-600">
            <div className="h-4 w-40 bg-navy-600 rounded" />
          </div>
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4].map((j) => (
              <div key={j} className="h-8 bg-navy-600 rounded" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default RecapPage;

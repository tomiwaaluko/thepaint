import type { GameSlate, OverUnderLine, FantasyProjection } from "../../types/chalk";
import { PlayerCard } from "../PlayerCard/PlayerCard";
import { PropsBoard } from "../PropsBoard/PropsBoard";
import { FantasyBoard } from "../FantasyBoard/FantasyBoard";
import { useState } from "react";

interface GameDetailViewProps {
  game: GameSlate;
  props: OverUnderLine[];
  fantasyProjections: FantasyProjection[];
}

type Tab = "players" | "props" | "fantasy";

export function GameDetailView({ game, props, fantasyProjections }: GameDetailViewProps) {
  const [tab, setTab] = useState<Tab>("players");

  return (
    <div>
      {/* Game header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-1">
        <h2 className="text-lg font-bold text-neutral-200">
          {game.away_team} @ {game.home_team}
        </h2>
        <div className="text-sm text-neutral-400">
          Projected Total:{" "}
          <span className="text-chalk-orange font-bold">
            {game.predicted_total.toFixed(1)}
          </span>
        </div>
      </div>

      {/* Tab bar — full width on mobile */}
      <div className="flex gap-1 mb-4 border-b border-navy-600 overflow-x-auto">
        {(["players", "props", "fantasy"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 md:px-4 py-2 text-sm font-medium transition-colors cursor-pointer capitalize whitespace-nowrap ${
              tab === t
                ? "text-chalk-orange border-b-2 border-chalk-orange"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {t === "props" ? "Props Board" : t === "fantasy" ? "Fantasy" : "Players"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "players" && (
        <div>
          <h3 className="text-xs text-neutral-400 uppercase font-bold mb-2">
            {game.away_team}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
            {game.away_predictions.map((p) => (
              <PlayerCard key={p.player_id} prediction={p} />
            ))}
          </div>

          <h3 className="text-xs text-neutral-400 uppercase font-bold mb-2">
            {game.home_team}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {game.home_predictions.map((p) => (
              <PlayerCard key={p.player_id} prediction={p} />
            ))}
          </div>
        </div>
      )}

      {tab === "props" && <PropsBoard props={props} />}

      {tab === "fantasy" && (
        <FantasyBoard projections={fantasyProjections} platform="draftkings" />
      )}
    </div>
  );
}

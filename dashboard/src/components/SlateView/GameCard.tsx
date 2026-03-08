interface GameCardProps {
  gameId: string;
  homeTeam: string;
  awayTeam: string;
  predictedTotal: number;
  playerCount: number;
  selected: boolean;
  onClick: () => void;
}

export function GameCard({
  homeTeam,
  awayTeam,
  predictedTotal,
  playerCount,
  selected,
  onClick,
}: GameCardProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-colors cursor-pointer ${
        selected
          ? "bg-navy-700 border-chalk-orange"
          : "bg-navy-800 border-navy-600 hover:border-neutral-400"
      }`}
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-bold text-neutral-200">{awayTeam}</span>
          <span className="text-xs text-neutral-400 mx-1.5">@</span>
          <span className="text-sm font-bold text-neutral-200">{homeTeam}</span>
        </div>
        <div className="text-right">
          <div className="text-xs text-neutral-400">O/U</div>
          <div className="text-sm font-bold text-chalk-orange">
            {predictedTotal.toFixed(1)}
          </div>
        </div>
      </div>
      <div className="text-xs text-neutral-400 mt-1">
        {playerCount} players projected
      </div>
    </button>
  );
}

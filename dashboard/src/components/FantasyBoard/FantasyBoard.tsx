import { useState } from "react";
import { ArrowUpDown } from "lucide-react";
import type { FantasyProjection } from "../../types/chalk";

interface FantasyBoardProps {
  projections: FantasyProjection[];
  platform: string;
}

type SortKey = "mean" | "floor" | "ceiling" | "boom_rate" | "bust_rate";

export function FantasyBoard({ projections, platform }: FantasyBoardProps) {
  const [sortKey, setSortKey] = useState<SortKey>("mean");
  const [showValueOnly, setShowValueOnly] = useState(false);

  const sorted = [...projections].sort((a, b) => {
    if (sortKey === "bust_rate") return a[sortKey] - b[sortKey]; // lower is better
    return b[sortKey] - a[sortKey];
  });

  const filtered = showValueOnly
    ? sorted.filter((p) => p.mean > 30)
    : sorted;

  const platformLabel =
    platform === "draftkings" ? "DK" : platform === "fanduel" ? "FD" : "Yahoo";

  return (
    <div>
      {/* Controls */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-xs text-neutral-400 uppercase font-bold">
          {platformLabel} Projections
        </span>
        <label className="flex items-center gap-1.5 text-xs text-neutral-400 cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={showValueOnly}
            onChange={(e) => setShowValueOnly(e.target.checked)}
            className="rounded border-navy-600 accent-chalk-orange"
          />
          Value plays only
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-neutral-400 uppercase border-b border-navy-600">
              <th className="text-left py-2 px-2">Player</th>
              <SortHeader label="Proj" sortKey="mean" current={sortKey} onSort={setSortKey} />
              <SortHeader label="Floor" sortKey="floor" current={sortKey} onSort={setSortKey} />
              <SortHeader label="Ceiling" sortKey="ceiling" current={sortKey} onSort={setSortKey} />
              <SortHeader label="Boom%" sortKey="boom_rate" current={sortKey} onSort={setSortKey} />
              <SortHeader label="Bust%" sortKey="bust_rate" current={sortKey} onSort={setSortKey} />
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              return (
                <tr
                  key={p.player_id}
                  className="border-b border-navy-700 hover:bg-navy-700/50"
                >
                  <td className="py-1.5 px-2 font-medium text-neutral-200">
                    {p.player_name || String(p.player_id)}
                  </td>
                  <td className="py-1.5 px-2 text-right font-bold text-neutral-200">
                    {p.mean.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-neutral-400">
                    {p.floor.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-neutral-300">
                    {p.ceiling.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    <span
                      className={
                        p.boom_rate >= 0.15
                          ? "text-value-green font-semibold"
                          : "text-neutral-400"
                      }
                    >
                      {(p.boom_rate * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    <span
                      className={
                        p.bust_rate >= 0.25
                          ? "text-fade-red font-semibold"
                          : "text-neutral-400"
                      }
                    >
                      {(p.bust_rate * 100).toFixed(0)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div className="text-center text-neutral-400 py-6 text-sm">
          No projections available
        </div>
      )}
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  current,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  onSort: (k: SortKey) => void;
}) {
  return (
    <th
      className="text-right py-2 px-2 cursor-pointer select-none hover:text-neutral-200 transition-colors"
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {current === sortKey && (
          <ArrowUpDown size={10} className="text-chalk-orange" />
        )}
      </span>
    </th>
  );
}

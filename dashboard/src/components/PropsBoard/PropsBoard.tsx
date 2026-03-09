import { useState } from "react";
import { Star } from "lucide-react";
import type { OverUnderLine } from "../../types/chalk";

interface PropsBoardProps {
  props: OverUnderLine[];
}

const STAT_LABELS: Record<string, string> = {
  pts: "PTS",
  reb: "REB",
  ast: "AST",
  fg3m: "3PM",
};

type FilterStat = "all" | string;
type FilterConf = "all" | "high" | "medium" | "low";

export function PropsBoard({ props }: PropsBoardProps) {
  const [statFilter, setStatFilter] = useState<FilterStat>("all");
  const [confFilter, setConfFilter] = useState<FilterConf>("all");

  const filtered = props
    .filter((p) => statFilter === "all" || p.stat === statFilter)
    .filter((p) => confFilter === "all" || p.confidence === confFilter)
    .sort((a, b) => Math.abs(b.edge) - Math.abs(a.edge));

  const uniqueStats = [...new Set(props.map((p) => p.stat))];

  return (
    <div>
      {/* Filters — wrap on mobile */}
      <div className="flex flex-wrap gap-2 mb-3">
        <FilterBtn
          active={statFilter === "all"}
          onClick={() => setStatFilter("all")}
        >
          All
        </FilterBtn>
        {uniqueStats.map((s) => (
          <FilterBtn
            key={s}
            active={statFilter === s}
            onClick={() => setStatFilter(s)}
          >
            {STAT_LABELS[s] ?? s}
          </FilterBtn>
        ))}
        <span className="mx-2 border-l border-navy-600" />
        <FilterBtn
          active={confFilter === "all"}
          onClick={() => setConfFilter("all")}
        >
          Any
        </FilterBtn>
        {(["high", "medium", "low"] as const).map((c) => (
          <FilterBtn
            key={c}
            active={confFilter === c}
            onClick={() => setConfFilter(c)}
          >
            {c}
          </FilterBtn>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-neutral-400 uppercase border-b border-navy-600">
              <th className="text-left py-2 px-2">Player</th>
              <th className="text-left py-2 px-1">Stat</th>
              <th className="text-right py-2 px-1">Line</th>
              <th className="text-right py-2 px-1">Model</th>
              <th className="text-right py-2 px-1">Over%</th>
              <th className="text-right py-2 px-2">Edge</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p, i) => {
              const isHighEdge = Math.abs(p.edge) >= 0.08;
              const rowBg =
                p.edge > 0.06
                  ? "bg-value-green/8"
                  : p.edge < -0.06
                    ? "bg-fade-red/8"
                    : "";

              return (
                <tr
                  key={`${p.player_id}-${p.stat}-${i}`}
                  className={`border-b border-navy-700 hover:bg-navy-700/50 ${rowBg}`}
                >
                  <td className="py-1.5 px-2 font-medium text-neutral-200">
                    {isHighEdge && (
                      <Star size={12} className="inline mr-1 text-yellow-400 fill-yellow-400" />
                    )}
                    {p.player_name}
                  </td>
                  <td className="py-1.5 px-1 text-neutral-400">
                    {STAT_LABELS[p.stat] ?? p.stat}
                  </td>
                  <td className="py-1.5 px-1 text-right text-neutral-300">
                    {p.line.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-1 text-right font-semibold text-neutral-200">
                    {/* Model's implied line is roughly the over_probability mapped back */}
                    {p.line.toFixed(1)}
                  </td>
                  <td className="py-1.5 px-1 text-right text-neutral-300">
                    {(p.over_probability * 100).toFixed(0)}%
                  </td>
                  <td className="py-1.5 px-2 text-right font-bold">
                    <EdgeBadge edge={p.edge} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div className="text-center text-neutral-400 py-6 text-sm">
          No props match the current filters
        </div>
      )}
    </div>
  );
}

function FilterBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer ${
        active
          ? "bg-chalk-orange text-white"
          : "bg-navy-700 text-neutral-400 hover:text-neutral-200"
      }`}
    >
      {children}
    </button>
  );
}

function EdgeBadge({ edge }: { edge: number }) {
  const pct = (edge * 100).toFixed(1);
  const sign = edge > 0 ? "+" : "";
  const color =
    edge > 0.04
      ? "text-value-green"
      : edge < -0.04
        ? "text-fade-red"
        : "text-neutral-400";

  return <span className={color}>{sign}{pct}%</span>;
}

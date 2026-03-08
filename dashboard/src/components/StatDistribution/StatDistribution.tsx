import type { StatPrediction } from "../../types/chalk";

interface StatDistributionProps {
  prediction: StatPrediction;
  vegasLine?: number;
  edge?: number;
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

export function StatDistribution({ prediction, vegasLine, edge }: StatDistributionProps) {
  const { stat, p10, p25, median, p75, ceiling } = prediction;
  const label = STAT_LABELS[stat] ?? stat.toUpperCase();

  // Scale: use p10-2 to ceiling+2 as range, minimum 0
  const rangeMin = Math.max(0, p10 - 2);
  const rangeMax = ceiling + 2;
  const range = rangeMax - rangeMin || 1;

  const toPercent = (val: number) => ((val - rangeMin) / range) * 100;

  const fullLeft = toPercent(p10);
  const fullWidth = toPercent(ceiling) - fullLeft;
  const iqrLeft = toPercent(p25);
  const iqrWidth = toPercent(p75) - iqrLeft;
  const medianPos = toPercent(median);

  // Vegas line styling
  let lineColor = "border-neutral-400";
  if (edge !== undefined) {
    if (edge > 0.04) lineColor = "border-value-green";
    else if (edge < -0.04) lineColor = "border-fade-red";
  }

  return (
    <div className="flex items-center gap-3 py-1">
      <span className="w-8 text-xs font-bold text-neutral-300 text-right shrink-0">
        {label}
      </span>

      <div className="relative flex-1 h-6">
        {/* Full range bar (p10 to p90) */}
        <div
          className="absolute top-2.5 h-1 rounded-full bg-navy-600"
          style={{ left: `${fullLeft}%`, width: `${fullWidth}%` }}
        />

        {/* IQR bar (p25 to p75) */}
        <div
          className="absolute top-1.5 h-3 rounded bg-chalk-orange/60"
          style={{ left: `${iqrLeft}%`, width: `${iqrWidth}%` }}
        />

        {/* Median marker */}
        <div
          className="absolute top-0.5 w-1.5 h-5 rounded-sm bg-chalk-orange"
          style={{ left: `${medianPos}%`, transform: "translateX(-50%)" }}
        />

        {/* Vegas line */}
        {vegasLine !== undefined && vegasLine >= rangeMin && vegasLine <= rangeMax && (
          <div
            className={`absolute top-0 h-6 border-l-2 border-dashed ${lineColor}`}
            style={{ left: `${toPercent(vegasLine)}%` }}
          />
        )}

        {/* Labels */}
        <span
          className="absolute -bottom-3.5 text-[10px] text-neutral-400"
          style={{ left: `${fullLeft}%`, transform: "translateX(-50%)" }}
        >
          {p10.toFixed(1)}
        </span>
        <span
          className="absolute -bottom-3.5 text-[10px] text-neutral-200 font-semibold"
          style={{ left: `${medianPos}%`, transform: "translateX(-50%)" }}
        >
          {median.toFixed(1)}
        </span>
        <span
          className="absolute -bottom-3.5 text-[10px] text-neutral-400"
          style={{ left: `${toPercent(ceiling)}%`, transform: "translateX(-50%)" }}
        >
          {ceiling.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

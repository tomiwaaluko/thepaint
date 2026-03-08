import type { PlayerPrediction } from "../../types/chalk";
import { InjuryBadge } from "../InjuryBadge/InjuryBadge";
import { StatDistribution } from "../StatDistribution/StatDistribution";
import { AlertTriangle } from "lucide-react";

interface PlayerCardProps {
  prediction: PlayerPrediction;
}

const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-value-green/20 text-value-green",
  medium: "bg-yellow-500/20 text-yellow-400",
  low: "bg-fade-red/20 text-fade-red",
};

const KEY_STATS = ["pts", "reb", "ast", "fg3m"];

export function PlayerCard({ prediction }: PlayerCardProps) {
  const {
    player_name,
    opponent_team,
    predictions,
    fantasy_scores,
    injury_context,
  } = prediction;

  const keyPreds = predictions.filter((p) => KEY_STATS.includes(p.stat));
  const overallConfidence = getOverallConfidence(keyPreds);

  return (
    <div className="bg-navy-800 rounded-lg border border-navy-600 p-4 hover:border-chalk-orange/40 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-neutral-200">{player_name}</h3>
          <span className="text-xs text-neutral-400">vs {opponent_team}</span>
        </div>
        <div className="flex items-center gap-2">
          <InjuryBadge status={injury_context.player_status} />
          <span
            className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${CONFIDENCE_STYLES[overallConfidence]}`}
          >
            {overallConfidence}
          </span>
        </div>
      </div>

      {/* Absent teammates alert */}
      {injury_context.absent_teammates.length > 0 && (
        <div className="flex items-center gap-1.5 mb-3 px-2 py-1 rounded bg-chalk-orange/10 border border-chalk-orange/30">
          <AlertTriangle size={12} className="text-chalk-orange shrink-0" />
          <span className="text-xs text-chalk-orange">
            Usage spike — {injury_context.absent_teammates.join(", ")}{" "}
            {injury_context.absent_teammates.length === 1 ? "is" : "are"} out
          </span>
        </div>
      )}

      {/* Stat distributions */}
      <div className="space-y-4 mb-4">
        {keyPreds.map((p) => (
          <StatDistribution key={p.stat} prediction={p} />
        ))}
      </div>

      {/* Fantasy scores */}
      <div className="flex gap-3 pt-2 border-t border-navy-600">
        <FantasyChip label="DK" value={fantasy_scores.draftkings} />
        <FantasyChip label="FD" value={fantasy_scores.fanduel} />
        <FantasyChip label="Yahoo" value={fantasy_scores.yahoo} />
      </div>
    </div>
  );
}

function FantasyChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <div className="text-[10px] text-neutral-400 uppercase">{label}</div>
      <div className="text-sm font-bold text-neutral-200">{value.toFixed(1)}</div>
    </div>
  );
}

function getOverallConfidence(
  preds: { confidence: "high" | "medium" | "low" }[]
): "high" | "medium" | "low" {
  const scores = { high: 3, medium: 2, low: 1 };
  if (preds.length === 0) return "medium";
  const avg =
    preds.reduce((sum, p) => sum + scores[p.confidence], 0) / preds.length;
  if (avg >= 2.5) return "high";
  if (avg >= 1.5) return "medium";
  return "low";
}

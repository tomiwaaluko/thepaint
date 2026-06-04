interface InjuryBadgeProps {
  status?: string | null;
}

const statusStyles: Record<string, string> = {
  active: "bg-value-green/20 text-value-green",
  questionable: "bg-yellow-500/20 text-yellow-400",
  doubtful: "bg-chalk-orange/20 text-chalk-orange-light",
  out: "bg-fade-red/20 text-fade-red",
};

export function InjuryBadge({ status }: InjuryBadgeProps) {
  const normalized = status?.trim() || "Active";
  const style = statusStyles[normalized.toLowerCase()] ?? statusStyles.active;
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1).toLowerCase();

  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${style}`}>
      {label}
    </span>
  );
}

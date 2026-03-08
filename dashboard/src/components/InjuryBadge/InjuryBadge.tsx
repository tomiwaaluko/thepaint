interface InjuryBadgeProps {
  status: string;
}

const statusStyles: Record<string, string> = {
  active: "bg-value-green/20 text-value-green",
  questionable: "bg-yellow-500/20 text-yellow-400",
  out: "bg-fade-red/20 text-fade-red",
};

export function InjuryBadge({ status }: InjuryBadgeProps) {
  const style = statusStyles[status.toLowerCase()] ?? statusStyles.active;
  const label = status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${style}`}>
      {label}
    </span>
  );
}

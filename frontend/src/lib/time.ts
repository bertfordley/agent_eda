export function relativeLabel(epochMs: number): string {
  const diffMs = Date.now() - epochMs;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return new Date(epochMs).toLocaleDateString();
}

export type DateGroupLabel = "Today" | "Yesterday" | "This Week" | "Older";

export function dateGroupLabel(epochMs: number): DateGroupLabel {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;
  const weekStart = todayStart - 6 * 86400000;
  if (epochMs >= todayStart) return "Today";
  if (epochMs >= yesterdayStart) return "Yesterday";
  if (epochMs >= weekStart) return "This Week";
  return "Older";
}

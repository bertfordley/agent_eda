import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/tooltip";
import type { ConnectionStatus } from "@/types";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { label: string; dotClass: string }
> = {
  connected: {
    label: "Connected",
    dotClass: "bg-emerald-500",
  },
  connecting: {
    label: "Connecting…",
    dotClass: "bg-amber-400 animate-pulse-slow",
  },
  disconnected: {
    label: "Offline",
    dotClass: "bg-zinc-500",
  },
  error: {
    label: "Connection error",
    dotClass: "bg-destructive animate-pulse-slow",
  },
};

export function ConnectionBadge() {
  const connection = useAppStore((s) => s.connection);
  const { label, dotClass } = STATUS_CONFIG[connection];

  return (
    <Tooltip content="Live agent WebSocket connection status">
      <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 select-none">
        <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", dotClass)} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
    </Tooltip>
  );
}

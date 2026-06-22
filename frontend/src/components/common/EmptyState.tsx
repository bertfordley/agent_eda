import type { LucideIcon } from "lucide-react";

interface EmptyStateProps { icon: LucideIcon; title: string; subtitle?: string; action?: React.ReactNode; }

export function EmptyState({ icon: Icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
      <Icon className="h-10 w-10 text-muted-foreground/50" strokeWidth={1.5} />
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

import type { LucideIcon } from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";

interface IconButtonProps {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  variant?: "ghost" | "default";
  disabled?: boolean;
  className?: string;
}

export function IconButton({
  icon: Icon,
  label,
  onClick,
  variant = "ghost",
  disabled = false,
  className,
}: IconButtonProps) {
  return (
    <Tooltip content={label}>
      <button
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        type="button"
        className={cn(
          "inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:pointer-events-none disabled:opacity-50",
          variant === "ghost"
            ? "hover:bg-muted text-muted-foreground hover:text-foreground"
            : "bg-primary text-primary-foreground hover:bg-primary/90",
          className
        )}
      >
        <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
      </button>
    </Tooltip>
  );
}

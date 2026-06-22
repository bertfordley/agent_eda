import * as React from "react";
import { cn } from "@/lib/cn";

interface DropdownMenuProps { trigger: React.ReactNode; children: React.ReactNode; align?: "left" | "right"; }

export function DropdownMenu({ trigger, children, align = "right" }: DropdownMenuProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    function handleClick(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);
  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((o) => !o)}>{trigger}</div>
      {open && (
        <div className={cn("absolute z-50 mt-1 min-w-[160px] rounded-md border border-border bg-card shadow-lg py-1", align === "right" ? "right-0" : "left-0")} onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}

export function DropdownMenuItem({ children, onClick, disabled, className }: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; className?: string }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={cn("w-full text-left px-3 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-50 disabled:pointer-events-none", className)}>
      {children}
    </button>
  );
}

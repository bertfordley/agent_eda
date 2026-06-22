import * as React from "react";
import { cn } from "@/lib/cn";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose} />
      <div className={cn("relative z-10 w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg", className)}>
        {title && (
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">{title}</h2>
            <button onClick={onClose} className="rounded-sm opacity-70 hover:opacity-100 transition-opacity"><X className="h-4 w-4" /></button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

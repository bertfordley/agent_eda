import * as React from "react";
import { cn } from "@/lib/cn";

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  viewportRef?: React.RefObject<HTMLDivElement | null>;
}

export function ScrollArea({
  className,
  children,
  viewportRef,
  ...props
}: ScrollAreaProps) {
  return (
    <div className={cn("relative overflow-hidden", className)} {...props}>
      <div
        ref={viewportRef}
        className="h-full w-full overflow-y-auto thin-scrollbar"
      >
        {children}
      </div>
    </div>
  );
}

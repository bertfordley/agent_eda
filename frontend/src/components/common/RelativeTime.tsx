import { useState, useEffect } from "react";
import { relativeLabel } from "@/lib/time";

interface RelativeTimeProps { epochMs: number; }

export function RelativeTime({ epochMs }: RelativeTimeProps) {
  const [label, setLabel] = useState(() => relativeLabel(epochMs));
  useEffect(() => {
    const interval = setInterval(() => setLabel(relativeLabel(epochMs)), 30000);
    return () => clearInterval(interval);
  }, [epochMs]);
  return <time dateTime={new Date(epochMs).toISOString()} className="text-xs text-muted-foreground">{label}</time>;
}

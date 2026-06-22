import { Globe, ExternalLink } from "lucide-react";
import type { LinkArtifact } from "@/types";
import { Button } from "@/components/ui/button";

interface LinkRendererProps {
  artifact: LinkArtifact;
}

export function LinkRenderer({ artifact }: LinkRendererProps) {
  let hostname = artifact.href;
  try { hostname = new URL(artifact.href).hostname; } catch { /* keep raw */ }
  const truncatedHref = artifact.href.length > 60 ? artifact.href.slice(0, 60) + "…" : artifact.href;
  return (
    <div className="flex flex-col h-full items-center justify-center p-6">
      <div className="flex flex-col items-center gap-4 rounded-xl border border-border bg-card p-8 text-center max-w-xs w-full">
        {artifact.faviconUrl ? (
          <img src={artifact.faviconUrl} alt={hostname} className="h-8 w-8 rounded"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
        ) : (
          <Globe className="h-8 w-8 text-primary/50" strokeWidth={1.5} />
        )}
        <div>
          <p className="font-medium text-sm">{hostname}</p>
          <p className="mt-1 text-xs text-muted-foreground break-all">{truncatedHref}</p>
        </div>
        <a href={artifact.href} target="_blank" rel="noopener noreferrer">
          <Button size="sm" className="gap-2">
            <ExternalLink className="h-4 w-4" />Open link
          </Button>
        </a>
      </div>
    </div>
  );
}

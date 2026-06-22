import { useState } from "react";
import { ImageOff, ExternalLink, Download } from "lucide-react";
import type { ChartImageArtifact } from "@/types";
import { Skeleton } from "@/components/ui/skeleton";
import { IconButton } from "@/components/common/IconButton";

interface ChartImageRendererProps {
  artifact: ChartImageArtifact;
}

export function ChartImageRenderer({ artifact }: ChartImageRendererProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
        <p className="flex-1 truncate text-sm font-medium">{artifact.title}</p>
        <IconButton
          icon={ExternalLink}
          label="Open chart in new tab"
          onClick={() => window.open(artifact.url, "_blank", "noopener,noreferrer")}
        />
        <a href={artifact.url} download={artifact.filename} tabIndex={-1}>
          <IconButton icon={Download} label="Download chart image" />
        </a>
      </div>

      {/* Image area */}
      <div className="flex flex-1 min-h-0 items-center justify-center p-4">
        {error ? (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <ImageOff className="h-8 w-8" aria-hidden="true" />
            <p className="text-sm">Failed to load chart</p>
            <a
              href={artifact.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary underline"
            >
              Try opening directly
            </a>
          </div>
        ) : (
          <>
            {!loaded && (
              <Skeleton className="h-48 w-full max-w-md rounded-md" />
            )}
            <img
              src={artifact.url}
              alt={artifact.title}
              onLoad={() => setLoaded(true)}
              onError={() => { setError(true); setLoaded(false); }}
              className={loaded ? "max-h-full max-w-full object-contain rounded-md shadow-sm" : "hidden"}
            />
          </>
        )}
      </div>
    </div>
  );
}

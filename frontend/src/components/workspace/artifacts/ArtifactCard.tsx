import { BarChart3, Table, FileText, Link as LinkIcon } from "lucide-react";
import type { Artifact, ChartImageArtifact } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { RelativeTime } from "@/components/common/RelativeTime";
import { cn } from "@/lib/cn";

const KIND_ICON = {
  chart_image: BarChart3,
  chart_interactive: BarChart3,
  table: Table,
  file: FileText,
  link: LinkIcon,
} as const;

interface ArtifactCardProps {
  artifact: Artifact;
  isActive: boolean;
}

export function ArtifactCard({ artifact, isActive }: ArtifactCardProps) {
  const openArtifactInWorkspace = useAppStore((s) => s.openArtifactInWorkspace);
  const Icon = KIND_ICON[artifact.kind];
  const isChartImage = artifact.kind === "chart_image";

  return (
    <button
      onClick={() => openArtifactInWorkspace(artifact.id)}
      className={cn(
        "flex flex-col gap-2 rounded-lg border p-3 text-left transition-all",
        "hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isActive
          ? "border-primary ring-1 ring-primary bg-primary/5"
          : "border-border"
      )}
      aria-pressed={isActive}
    >
      {/* Thumbnail */}
      {isChartImage ? (
        <div className="w-full h-24 rounded-md overflow-hidden bg-muted">
          <img
            src={(artifact as ChartImageArtifact).url}
            alt={artifact.title}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        </div>
      ) : (
        <div className="flex h-24 w-full items-center justify-center rounded-md bg-muted">
          <Icon
            className="h-8 w-8 text-muted-foreground/40"
            strokeWidth={1.5}
            aria-hidden="true"
          />
        </div>
      )}

      {/* Metadata */}
      <div className="min-w-0">
        <p className="line-clamp-2 text-xs font-medium leading-tight">
          {artifact.title}
        </p>
        <div className="mt-0.5">
          <RelativeTime epochMs={artifact.createdAt} />
        </div>
      </div>
    </button>
  );
}

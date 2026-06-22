import { BarChart3, Table, FileText, Link as LinkIcon } from "lucide-react";
import type { Artifact } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/cn";

interface ArtifactChipProps {
  artifact: Artifact;
}

const KIND_ICON: Record<Artifact["kind"], typeof BarChart3> = {
  chart_image: BarChart3,
  chart_interactive: BarChart3,
  table: Table,
  file: FileText,
  link: LinkIcon,
};

const KIND_LABEL: Record<Artifact["kind"], string> = {
  chart_image: "Chart",
  chart_interactive: "Interactive chart",
  table: "Table",
  file: "File",
  link: "Link",
};

export function ArtifactChip({ artifact }: ArtifactChipProps) {
  const openArtifactInWorkspace = useAppStore((s) => s.openArtifactInWorkspace);
  const Icon = KIND_ICON[artifact.kind];
  const kindLabel = KIND_LABEL[artifact.kind];
  const truncatedTitle =
    artifact.title.length > 28
      ? artifact.title.slice(0, 28) + "…"
      : artifact.title;

  return (
    <button
      type="button"
      onClick={() => openArtifactInWorkspace(artifact.id)}
      aria-label={`Open ${kindLabel}: ${artifact.title}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-xs",
        "transition-colors hover:border-primary hover:bg-primary/5 cursor-pointer",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <Icon className="h-3 w-3 text-primary shrink-0" aria-hidden="true" />
      <span className="text-muted-foreground">{truncatedTitle}</span>
    </button>
  );
}

import { ChevronLeft } from "lucide-react";
import type { Artifact } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { IconButton } from "@/components/common/IconButton";
import { ChartImageRenderer } from "./ChartImageRenderer";
import { ChartInteractiveRenderer } from "./ChartInteractiveRenderer";
import { TableRenderer } from "./TableRenderer";
import { FileRenderer } from "./FileRenderer";
import { LinkRenderer } from "./LinkRenderer";

interface ArtifactViewerProps {
  artifact: Artifact;
}

export function ArtifactViewer({ artifact }: ArtifactViewerProps) {
  function handleBack() {
    useAppStore.setState((s) => ({
      workspace: { ...s.workspace, selectedArtifactId: null },
    }));
  }

  return (
    <div className="flex flex-col h-full">
      {/* Back navigation bar */}
      <div className="flex items-center gap-1 border-b border-border px-2 py-1.5 shrink-0">
        <IconButton
          icon={ChevronLeft}
          label="Back to artifact list"
          onClick={handleBack}
        />
        <p className="text-xs text-muted-foreground truncate flex-1 pl-1">
          {artifact.title}
        </p>
      </div>

      {/* Renderer area fills remaining height */}
      <div className="flex flex-col flex-1 min-h-0">
        {artifact.kind === "chart_image" && (
          <ChartImageRenderer artifact={artifact} />
        )}
        {artifact.kind === "chart_interactive" && (
          <ChartInteractiveRenderer artifact={artifact} />
        )}
        {artifact.kind === "table" && (
          <TableRenderer artifact={artifact} />
        )}
        {artifact.kind === "file" && (
          <FileRenderer artifact={artifact} />
        )}
        {artifact.kind === "link" && (
          <LinkRenderer artifact={artifact} />
        )}
      </div>
    </div>
  );
}

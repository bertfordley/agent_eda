import { FileText, Download } from "lucide-react";
import type { FileArtifact } from "@/types";
import { Button } from "@/components/ui/button";

interface FileRendererProps {
  artifact: FileArtifact;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileRenderer({ artifact }: FileRendererProps) {
  return (
    <div className="flex flex-col h-full items-center justify-center p-6">
      <div className="flex flex-col items-center gap-4 rounded-xl border border-border bg-card p-8 text-center max-w-xs w-full">
        <FileText className="h-12 w-12 text-primary/50" strokeWidth={1.5} />
        <div>
          <p className="font-medium text-sm break-all">{artifact.filename}</p>
          <p className="mt-1 text-xs text-muted-foreground">{artifact.mimeType}</p>
          <p className="text-xs text-muted-foreground">{formatBytes(artifact.sizeBytes)}</p>
        </div>
        <a href={artifact.url} download={artifact.filename}>
          <Button size="sm" className="gap-2">
            <Download className="h-4 w-4" />Download
          </Button>
        </a>
      </div>
    </div>
  );
}

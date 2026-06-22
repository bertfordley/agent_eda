import { ExternalLink } from "lucide-react";
import type { ChartInteractiveArtifact } from "@/types";
import { IconButton } from "@/components/common/IconButton";

interface ChartInteractiveRendererProps {
  artifact: ChartInteractiveArtifact;
}

export function ChartInteractiveRenderer({ artifact }: ChartInteractiveRendererProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
        <p className="flex-1 truncate text-sm font-medium">{artifact.title}</p>
        <IconButton
          icon={ExternalLink}
          label="Open in new tab"
          onClick={() => window.open(artifact.url, "_blank", "noopener,noreferrer")}
        />
      </div>
      <div className="flex-1 min-h-0 p-3">
        {/*
          TICKET-013: sandbox uses allow-scripts WITHOUT allow-same-origin.

          Combining allow-scripts + allow-same-origin on content served from
          the same origin allows the framed document to escape the sandbox and
          script the parent context. Plotly self-contained HTML executes
          correctly with allow-scripts alone — it bundles its own runtime and
          does not need cross-frame DOM access.

          NEVER re-add allow-same-origin here without re-evaluating XSS risk
          from LLM-influenced chart data (column names, category labels) that
          flows into the iframe's HTML content.
        */}
        <iframe
          src={artifact.url}
          title={artifact.title}
          sandbox="allow-scripts"
          className="h-full w-full rounded-md bg-white"
        />
      </div>
    </div>
  );
}

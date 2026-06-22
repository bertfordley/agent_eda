import { BarChart3 } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/common/EmptyState";
import { ArtifactCard } from "./ArtifactCard";

export function ArtifactList() {
  const artifacts = useAppStore((s) => s.artifacts);
  const workspace = useAppStore((s) => s.workspace);
  const sorted = Object.values(artifacts).sort((a, b) => b.createdAt - a.createdAt);

  return (
    <ScrollArea className="flex-1 min-h-0">
      {sorted.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No artifacts yet"
          subtitle="Charts and tables generated during the chat will appear here."
        />
      ) : (
        <div className="grid grid-cols-2 gap-2 p-3">
          {sorted.map((a) => (
            <ArtifactCard
              key={a.id}
              artifact={a}
              isActive={workspace.selectedArtifactId === a.id}
            />
          ))}
        </div>
      )}
    </ScrollArea>
  );
}

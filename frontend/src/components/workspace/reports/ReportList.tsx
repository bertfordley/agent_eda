import { FileText } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/common/EmptyState";
import { ReportCard } from "./ReportCard";

export function ReportList() {
  const reports = useAppStore((s) => s.reports);
  const workspace = useAppStore((s) => s.workspace);
  const sorted = Object.values(reports).sort((a, b) => b.createdAt - a.createdAt);

  return (
    <ScrollArea className="flex-1 min-h-0">
      {sorted.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No reports yet"
          subtitle='Ask the agent to "build an HTML report of monthly trends" to generate one.'
        />
      ) : (
        <div className="flex flex-col gap-1 p-3">
          {sorted.map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              isActive={workspace.selectedReportId === r.id}
            />
          ))}
        </div>
      )}
    </ScrollArea>
  );
}

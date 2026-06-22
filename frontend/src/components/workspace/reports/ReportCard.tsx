import { FileText } from "lucide-react";
import type { Report } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { RelativeTime } from "@/components/common/RelativeTime";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

interface ReportCardProps {
  report: Report;
  isActive: boolean;
}

export function ReportCard({ report, isActive }: ReportCardProps) {
  const openReportInWorkspace = useAppStore((s) => s.openReportInWorkspace);
  return (
    <button
      onClick={() => openReportInWorkspace(report.id)}
      className={cn(
        "flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors",
        isActive ? "bg-primary/10 border border-primary/30" : "hover:bg-muted border border-transparent"
      )}
    >
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium">{report.title}</p>
        <RelativeTime epochMs={report.createdAt} />
      </div>
      <Badge variant="secondary">{report.format.toUpperCase()}</Badge>
    </button>
  );
}

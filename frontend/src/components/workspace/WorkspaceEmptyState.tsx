import { PanelRight } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";

export function WorkspaceEmptyState() {
  return (
    <div className="flex flex-1 min-h-0 items-center justify-center">
      <EmptyState icon={PanelRight} title="Nothing open" subtitle="Select an artifact or report to view it here." />
    </div>
  );
}

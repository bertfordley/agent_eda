import { useAppStore } from "@/store/useAppStore";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import type { WorkspaceTab } from "@/types";

export function WorkspaceTabs() {
  const workspace = useAppStore((s) => s.workspace);
  const setWorkspaceTab = useAppStore((s) => s.setWorkspaceTab);
  const artifactCount = useAppStore((s) => Object.keys(s.artifacts).length);
  const reportCount = useAppStore((s) => Object.keys(s.reports).length);

  return (
    <Tabs
      value={workspace.activeTab}
      onValueChange={(v) => setWorkspaceTab(v as WorkspaceTab)}
      className="w-auto"
    >
      <TabsList>
        <TabsTrigger value="reports">
          Reports
          {reportCount > 0 && (
            <Badge
              variant="secondary"
              className="ml-1.5 h-4 min-w-[16px] px-1 text-[10px]"
            >
              {reportCount}
            </Badge>
          )}
        </TabsTrigger>
        <TabsTrigger value="artifacts">
          Artifacts
          {artifactCount > 0 && (
            <Badge
              variant="secondary"
              className="ml-1.5 h-4 min-w-[16px] px-1 text-[10px]"
            >
              {artifactCount}
            </Badge>
          )}
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}

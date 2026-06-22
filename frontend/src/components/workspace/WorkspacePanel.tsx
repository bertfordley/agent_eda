import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import { IconButton } from "@/components/common/IconButton";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { WorkspaceEmptyState } from "./WorkspaceEmptyState";
import { ReportList } from "./reports/ReportList";
import { ReportViewer } from "./reports/ReportViewer";
import { ArtifactList } from "./artifacts/ArtifactList";
import { ArtifactViewer } from "./artifacts/ArtifactViewer";
import { useIsDesktop } from "@/hooks/useMediaQuery";

const SPRING = { type: "spring", damping: 30, stiffness: 300 } as const;

export function WorkspacePanel() {
  const workspace = useAppStore((s) => s.workspace);
  const closeWorkspace = useAppStore((s) => s.closeWorkspace);
  const artifacts = useAppStore((s) => s.artifacts);
  const reports = useAppStore((s) => s.reports);
  const isDesktop = useIsDesktop();

  const selectedArtifact = workspace.selectedArtifactId
    ? artifacts[workspace.selectedArtifactId]
    : null;
  const selectedReport = workspace.selectedReportId
    ? reports[workspace.selectedReportId]
    : null;

  const artifactCount = Object.keys(artifacts).length;
  const reportCount = Object.keys(reports).length;
  const hasAnyContent = artifactCount > 0 || reportCount > 0;

  const panelContent = (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Header: tabs + close button */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 shrink-0">
        <WorkspaceTabs />
        <IconButton icon={X} label="Close workspace panel" onClick={closeWorkspace} />
      </div>

      {/* Body: switches between report and artifact views */}
      <div className="flex flex-col flex-1 min-h-0">
        {workspace.activeTab === "reports" && (
          selectedReport
            ? <ReportViewer report={selectedReport} />
            : <ReportList />
        )}
        {workspace.activeTab === "artifacts" && (
          selectedArtifact
            ? <ArtifactViewer artifact={selectedArtifact} />
            : hasAnyContent
            ? <ArtifactList />
            : <WorkspaceEmptyState />
        )}
      </div>
    </div>
  );

  if (!isDesktop) {
    // Mobile: full-screen overlay.
    return (
      <AnimatePresence>
        {workspace.isOpen && (
          <motion.div
            key="workspace-mobile"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40"
          >
            {panelContent}
          </motion.div>
        )}
      </AnimatePresence>
    );
  }

  // Desktop: inline panel that slides in from the right.
  return (
    <AnimatePresence initial={false}>
      {workspace.isOpen && (
        <motion.div
          key="workspace-desktop"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: "40%", opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={SPRING}
          style={{ minWidth: 0 }}
          className="overflow-hidden shrink-0"
        >
          {panelContent}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

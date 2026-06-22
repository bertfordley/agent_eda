import { useAppStore } from "@/store/useAppStore";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { HistorySidebar } from "@/components/history/HistorySidebar";
import { ChatColumn } from "@/components/chat/ChatColumn";
import { WorkspacePanel } from "@/components/workspace/WorkspacePanel";

export function AppShell() {
  const isDesktop = useIsDesktop();
  const isWorkspaceOpen = useAppStore((s) => s.workspace.isOpen);

  if (!isDesktop) {
    // Mobile: ChatColumn takes full width. HistorySidebar and WorkspacePanel
    // each render as fixed overlays — their framer-motion AnimatePresence
    // blocks handle that internally.
    return (
      <div className="relative flex flex-1 min-h-0 overflow-hidden">
        <ChatColumn />
        <HistorySidebar />
        <WorkspacePanel />
      </div>
    );
  }

  // Desktop: three-zone horizontal layout.
  // HistorySidebar animates its own width 280→0 when toggled; the flex container
  // expands into the freed space naturally.
  // WorkspacePanel animates its own width ~40%→0 when closed; ChatColumn
  // absorbs the freed space because it has flex-1.
  // We impose a minimum width on ChatColumn so it never gets crushed when both
  // panels are open at once.
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      <HistorySidebar />
      <div
        className="flex flex-col flex-1 min-h-0 min-w-0"
        style={{ minWidth: isWorkspaceOpen ? 480 : 320 }}
      >
        <ChatColumn />
      </div>
      <WorkspacePanel />
    </div>
  );
}

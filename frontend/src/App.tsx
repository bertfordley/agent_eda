import { Toaster } from "sonner";
import { TopBar } from "@/components/layout/TopBar";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { useChatStream } from "@/hooks/useChatStream";
import { useArtifactPolling } from "@/hooks/useArtifactPolling";

/**
 * AppInner mounts the two application-level side effects:
 *   1. useChatStream() — creates the singleton WebSocket client that connects
 *      to the FastAPI /chat/stream endpoint. Composer and ChatEmptyState also
 *      call this hook to obtain sendMessage, but they share the same module-level
 *      client via the singleton pattern — no duplicate connections are created.
 *   2. useArtifactPolling() — polls /charts and /reports every 4 s and registers
 *      new files as artifacts/reports in the store.
 *
 * Both hooks must run in a component that is always mounted for the app's
 * lifetime, which is why they live here rather than deeper in the tree.
 */
function AppInner() {
  useChatStream();
  useArtifactPolling();

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <TopBar />
      <AppShell />
      <Toaster richColors position="bottom-right" />
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary fallbackTitle="EDA Agent failed to load">
      <AppInner />
    </ErrorBoundary>
  );
}

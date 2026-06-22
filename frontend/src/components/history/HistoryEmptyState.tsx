import { MessageSquare } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
export function HistoryEmptyState() {
  return <EmptyState icon={MessageSquare} title="No conversations yet" subtitle="Start a new chat to begin." />;
}

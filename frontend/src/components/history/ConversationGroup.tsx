import type { Conversation } from "@/types";
import { ConversationItem } from "./ConversationItem";
import { useAppStore } from "@/store/useAppStore";

interface ConversationGroupProps { label: string; conversations: Conversation[]; }

export function ConversationGroup({ label, conversations }: ConversationGroupProps) {
  const activeConversationId = useAppStore((s) => s.activeConversationId);
  return (
    <div className="mb-2">
      <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <div className="flex flex-col gap-0.5">
        {conversations.map((conv) => <ConversationItem key={conv.id} conversation={conv} isActive={conv.id === activeConversationId} />)}
      </div>
    </div>
  );
}

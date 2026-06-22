import { useAppStore } from "@/store/useAppStore";
import { MessageList } from "./MessageList";
import { ChatEmptyState } from "./ChatEmptyState";
import { Composer } from "./Composer";

export function ChatColumn() {
  const activeConversationId = useAppStore((s) => s.activeConversationId);
  const conversations = useAppStore((s) => s.conversations);

  const conversation = activeConversationId
    ? conversations[activeConversationId]
    : null;
  const hasMessages = (conversation?.messageIds.length ?? 0) > 0;

  return (
    <div className="flex flex-col flex-1 min-w-0 min-h-0">
      {/* Message area or welcome screen */}
      {hasMessages ? <MessageList /> : <ChatEmptyState />}

      {/* Composer always pinned to the bottom */}
      <Composer />
    </div>
  );
}

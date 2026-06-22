import { useEffect, useRef } from "react";
import { useAppStore } from "@/store/useAppStore";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble } from "./MessageBubble";
import { MessageSkeleton } from "./MessageSkeleton";

export function MessageList() {
  const activeConversationId = useAppStore((s) => s.activeConversationId);
  const conversations = useAppStore((s) => s.conversations);
  const messages = useAppStore((s) => s.messages);
  const isAwaitingResponse = useAppStore((s) => s.isAwaitingResponse);

  const viewportRef = useRef<HTMLDivElement | null>(null);

  const conversation = activeConversationId
    ? conversations[activeConversationId]
    : null;

  const orderedMessages = (conversation?.messageIds ?? [])
    .map((id) => messages[id])
    .filter(Boolean);

  const lastMsg = orderedMessages[orderedMessages.length - 1];
  const lastMsgContent = lastMsg?.content ?? "";
  const lastMsgCount = orderedMessages.length;

  // Scroll to bottom whenever new messages arrive or streaming content grows.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    // Use requestAnimationFrame to scroll after the DOM has painted the new content.
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [lastMsgCount, lastMsgContent]);

  // Show the skeleton when we're waiting for the first token of a new response.
  const showSkeleton =
    isAwaitingResponse &&
    (orderedMessages.length === 0 || lastMsg?.status !== "streaming");

  return (
    <ScrollArea viewportRef={viewportRef} className="flex-1 min-h-0">
      <div
        className="mx-auto max-w-3xl px-4 py-6 flex flex-col gap-4"
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
        aria-atomic="false"
      >
        {orderedMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {showSkeleton && <MessageSkeleton />}
      </div>
    </ScrollArea>
  );
}

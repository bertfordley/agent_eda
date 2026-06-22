import { useRef, useEffect, useCallback } from "react";
import { SendHorizontal } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { useChatStream } from "@/hooks/useChatStream";
import { Textarea } from "@/components/ui/textarea";
import { DropZone } from "./DropZone";
import { cn } from "@/lib/cn";

export function Composer() {
  const composerValue = useAppStore((s) => s.composerValue);
  const setComposerValue = useAppStore((s) => s.setComposerValue);
  const isAwaitingResponse = useAppStore((s) => s.isAwaitingResponse);
  const connection = useAppStore((s) => s.connection);

  // useChatStream is safe to call here — it shares the singleton WebSocket
  // client created in App.tsx. No duplicate connections are opened.
  const { sendMessage } = useChatStream();

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend =
    composerValue.trim().length > 0 &&
    !isAwaitingResponse &&
    connection === "connected";

  const submit = useCallback(() => {
    if (!canSend) return;
    sendMessage(composerValue);
    setComposerValue("");
    // Reset textarea height after clearing.
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [canSend, composerValue, sendMessage, setComposerValue]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  // Auto-grow the textarea as the user types (max 8 rows ≈ 200px).
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [composerValue]);

  return (
    <DropZone>
      <div className="border-t border-border bg-card px-4 py-3">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-xl border border-border bg-muted/30 px-3 py-2 focus-within:border-primary/50 transition-colors">
            <Textarea
              ref={textareaRef}
              value={composerValue}
              onChange={(e) => setComposerValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your data…"
              rows={1}
              aria-label="Chat message input"
              disabled={isAwaitingResponse}
              className={cn(
                "flex-1 min-h-[36px] max-h-[200px] border-0 bg-transparent p-0 shadow-none",
                "focus-visible:ring-0 resize-none text-sm"
              )}
            />
            <button
              onClick={submit}
              disabled={!canSend}
              aria-label="Send message"
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                canSend
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed opacity-50"
              )}
            >
              <SendHorizontal className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          <p className="mt-1.5 text-center text-[10px] text-muted-foreground select-none">
            {connection !== "connected"
              ? "Reconnecting to agent…"
              : "Enter to send · Shift+Enter for new line"}
          </p>
        </div>
      </div>
    </DropZone>
  );
}

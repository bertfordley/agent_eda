import { Bot, AlertCircle } from "lucide-react";
import type { ChatMessage } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/cn";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ArtifactChip } from "./ArtifactChip";
import { StreamingCursor } from "./StreamingCursor";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const artifacts = useAppStore((s) => s.artifacts);

  // ── User message ────────────────────────────────────────────────────────────
  if (message.role === "user") {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  // ── System message ──────────────────────────────────────────────────────────
  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-muted-foreground py-1 px-2 rounded-full bg-muted/50">
          {message.content}
        </span>
      </div>
    );
  }

  // ── Assistant message ───────────────────────────────────────────────────────
  const resolvedArtifacts = message.artifactIds
    .map((id) => artifacts[id])
    .filter(Boolean);

  return (
    <div className="flex items-start gap-3 animate-fade-in">
      {/* Bot avatar */}
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 mt-0.5"
        aria-hidden="true"
      >
        <Bot className="h-4 w-4 text-primary" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Message body */}
        <div
          className={cn(
            "rounded-2xl rounded-tl-sm border px-4 py-3",
            message.status === "error"
              ? "border-destructive/50 bg-destructive/5"
              : "border-border bg-card"
          )}
        >
          {message.status === "error" ? (
            <div className="flex items-start gap-2">
              <AlertCircle
                className="h-4 w-4 text-destructive shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm text-destructive font-medium">Agent error</p>
                {message.errorText && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {message.errorText}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <>
              {/* Empty content placeholder while agent is thinking (before first token) */}
              {message.content.length === 0 && message.status === "streaming" ? (
                <span className="text-sm text-muted-foreground italic">
                  Thinking…
                </span>
              ) : (
                <MarkdownRenderer content={message.content} />
              )}
              {message.status === "streaming" && <StreamingCursor />}
            </>
          )}
        </div>

        {/* Artifact chips below the bubble */}
        {resolvedArtifacts.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5" role="list" aria-label="Generated artifacts">
            {resolvedArtifacts.map((artifact) => (
              <div key={artifact.id} role="listitem">
                <ArtifactChip artifact={artifact} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

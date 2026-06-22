import { Sparkles } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";
import { SuggestedPrompts } from "./SuggestedPrompts";

export function ChatEmptyState() {
  // useChatStream is safe to call here — it shares the module-level singleton
  // WebSocket client. No additional connection is opened.
  const { sendMessage } = useChatStream();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-12 animate-fade-in">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Sparkles className="h-6 w-6 text-primary" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-base font-semibold">What would you like to analyze?</h2>
          <p className="mt-1 text-sm text-muted-foreground max-w-xs">
            Ask about your BigQuery data, paste a Google Sheet link, or request a
            chart or report.
          </p>
        </div>
      </div>

      <SuggestedPrompts onPick={sendMessage} />
    </div>
  );
}

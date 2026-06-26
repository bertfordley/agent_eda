import { WS_BASE_URL } from "@/lib/config";
import type { ConnectionStatus } from "@/types";

// TICKET-012: extended callback interface to handle structured tool-activity
// frames sent by the backend (TICKET-011). onToolStart and onToolEnd are
// optional so existing call-sites do not need to be updated.
// TICKET-1.3: subagent lifecycle callbacks added alongside the existing tool
// callbacks. All three are optional; existing call-sites compile unchanged.
export interface ChatStreamCallbacks {
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  onStatusChange: (status: ConnectionStatus) => void;
  onToolStart?: (tool: string, input: string) => void;
  onToolEnd?: (tool: string) => void;
  onSubagentStart?: (name: string) => void;
  onSubagentEnd?: (name: string) => void;
  // ns is the LangGraph namespace segment (e.g. "tools:<uuid>").
  // Do NOT route this through onToken — subagent text must stay separate.
  onSubagentToken?: (ns: string, text: string) => void;
  // Called when the server sends {"type":"thread","thread_id":"..."}.  The
  // server emits this only when it generated the id (client sent no thread_id).
  // Callers must persist it and send it with every subsequent turn.
  onThreadId?: (threadId: string) => void;
}

export class ChatStreamClient {
  private ws: WebSocket | null = null;
  private callbacks: ChatStreamCallbacks;
  private explicitlyClosed = false;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 5;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(callbacks: ChatStreamCallbacks) {
    this.callbacks = callbacks;
  }

  connect(): void {
    this.explicitlyClosed = false;
    this._openSocket();
  }

  private _openSocket(): void {
    this.callbacks.onStatusChange("connecting");
    const ws = new WebSocket(`${WS_BASE_URL}/chat/stream`);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onStatusChange("connected");
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      const data = event.data;
      try {
        const parsed: unknown = JSON.parse(data);

        // Only process structured frames when parsed value is a plain object.
        if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
          const frame = parsed as Record<string, unknown>;

          // Terminal control frames.
          if ("done" in frame) {
            this.callbacks.onDone();
            return;
          }
          if ("error" in frame) {
            this.callbacks.onError(String(frame.error));
            return;
          }

          // TICKET-4.1: thread identity frame.  Emitted by the server when it
          // generated the thread_id (client sent none).  Must be handled first
          // — never forward as a token.
          if (frame.type === "thread") {
            this.callbacks.onThreadId?.(String(frame.thread_id ?? ""));
            return;
          }

          // TICKET-012: structured tool-activity frames from TICKET-011.
          // Handle before falling through to onToken so they are never
          // emitted as raw JSON text into the chat message.
          if (frame.type === "tool_start") {
            this.callbacks.onToolStart?.(
              String(frame.tool ?? ""),
              String(frame.input ?? ""),
            );
            return;
          }
          if (frame.type === "tool_end") {
            this.callbacks.onToolEnd?.(String(frame.tool ?? ""));
            return;
          }

          // TICKET-1.3: subagent lifecycle and token frames.
          // Must be handled before the silent-discard fallthrough so raw JSON
          // never appears in the chat message body.
          if (frame.type === "subagent_start") {
            this.callbacks.onSubagentStart?.(String(frame.name ?? ""));
            return;
          }
          if (frame.type === "subagent_end") {
            this.callbacks.onSubagentEnd?.(String(frame.name ?? ""));
            return;
          }
          if (frame.type === "subagent_token") {
            // Deliberately NOT routed through onToken: subagent text must be
            // handled separately so it doesn't interleave uncontrolled with
            // main-agent tokens in the message body.
            this.callbacks.onSubagentToken?.(
              String(frame.ns ?? ""),
              String(frame.text ?? ""),
            );
            return;
          }

          // Any other unrecognised object frame: discard silently.
          // Never forward an unrecognised object as a token.
          return;
        }

        // Bare string token (server used send_text with a JSON-encoded string).
        if (typeof parsed === "string") {
          this.callbacks.onToken(parsed);
          return;
        }

        // Parsed to a non-object, non-string value — treat raw string as token.
        this.callbacks.onToken(data);
      } catch {
        // JSON.parse threw — the payload is a raw text token.
        this.callbacks.onToken(data);
      }
    };

    ws.onclose = () => {
      if (this.explicitlyClosed) {
        this.callbacks.onStatusChange("disconnected");
        return;
      }
      this.callbacks.onStatusChange("error");
      this._scheduleReconnect();
    };

    ws.onerror = () => {
      this.callbacks.onStatusChange("error");
    };
  }

  private _scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    const delay = Math.pow(2, this.reconnectAttempts) * 1000;
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      if (!this.explicitlyClosed) this._openSocket();
    }, delay);
  }

  // The client always sends { message, thread_id, messages } on every turn.
  // The server ignores messages when persistence is enabled (uses checkpointer);
  // uses it in dev fallback mode (checkpoint_enabled=false). No client branching.
  send(
    message: string,
    threadId?: string,
    messages?: Array<{ role: string; content: string }>,
  ): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const payload: Record<string, unknown> = { message };
      if (threadId) payload.thread_id = threadId;
      if (messages) payload.messages = messages;
      this.ws.send(JSON.stringify(payload));
    }
  }

  disconnect(): void {
    this.explicitlyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

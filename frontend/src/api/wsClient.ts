import { WS_BASE_URL } from "@/lib/config";
import type { ConnectionStatus } from "@/types";

// TICKET-012: extended callback interface to handle structured tool-activity
// frames sent by the backend (TICKET-011). onToolStart and onToolEnd are
// optional so existing call-sites do not need to be updated.
export interface ChatStreamCallbacks {
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  onStatusChange: (status: ConnectionStatus) => void;
  onToolStart?: (tool: string, input: string) => void;
  onToolEnd?: (tool: string) => void;
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

  send(message: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ message }));
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

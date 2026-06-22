/**
 * useChatStream — singleton WebSocket chat hook.
 *
 * Multiple components (App, Composer, ChatEmptyState) call this hook to
 * obtain sendMessage. All share a single module-level ChatStreamClient
 * instance — no duplicate connections are ever opened.
 *
 * TICKET-012: wires onToolStart / onToolEnd callbacks so the UI can
 * show "Running bq_run_query…" during the silent gap between send and
 * the first text token arriving.
 */
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useAppStore } from "@/store/useAppStore";
import { ChatStreamClient } from "@/api/wsClient";
import { detectArtifactsInText } from "@/lib/artifactDetection";
import type { ConnectionStatus } from "@/types";

// Module-level singletons: shared across all hook instances in the same page.
let _client: ChatStreamClient | null = null;
let _currentAssistantId: string | null = null;
let _mountCount = 0;

export function useChatStream(): {
  sendMessage: (text: string) => void;
  connectionStatus: ConnectionStatus;
} {
  const setConnection = useAppStore((s) => s.setConnection);
  const connection = useAppStore((s) => s.connection);
  const activeConversationId = useAppStore((s) => s.activeConversationId);
  const appendUserMessage = useAppStore((s) => s.appendUserMessage);
  const beginAssistantMessage = useAppStore((s) => s.beginAssistantMessage);
  const appendAssistantToken = useAppStore((s) => s.appendAssistantToken);
  const completeAssistantMessage = useAppStore((s) => s.completeAssistantMessage);
  const failAssistantMessage = useAppStore((s) => s.failAssistantMessage);
  const registerArtifact = useAppStore((s) => s.registerArtifact);
  const linkArtifactToMessage = useAppStore((s) => s.linkArtifactToMessage);
  const createConversation = useAppStore((s) => s.createConversation);
  const messages = useAppStore((s) => s.messages);

  // Mutable refs so WebSocket callbacks always see the latest state values
  // without needing to be recreated when state changes.
  const activeConvRef = useRef(activeConversationId);
  const messagesRef = useRef(messages);
  activeConvRef.current = activeConversationId;
  messagesRef.current = messages;

  // Bundle all store actions into one ref so the effect closure stays stable.
  const actionsRef = useRef({
    setConnection,
    appendAssistantToken,
    completeAssistantMessage,
    failAssistantMessage,
    registerArtifact,
    linkArtifactToMessage,
    beginAssistantMessage,
    appendUserMessage,
    createConversation,
  });
  actionsRef.current = {
    setConnection,
    appendAssistantToken,
    completeAssistantMessage,
    failAssistantMessage,
    registerArtifact,
    linkArtifactToMessage,
    beginAssistantMessage,
    appendUserMessage,
    createConversation,
  };

  useEffect(() => {
    _mountCount++;

    // Only the first mounted call-site creates the WebSocket client.
    if (_mountCount === 1) {
      const client = new ChatStreamClient({
        onStatusChange: (status) => {
          actionsRef.current.setConnection(status);
        },

        onToken: (token) => {
          if (_currentAssistantId) {
            actionsRef.current.appendAssistantToken(_currentAssistantId, token);
          }
        },

        onDone: () => {
          const id = _currentAssistantId;
          if (!id) return;
          // Detect artifacts embedded in the completed message text.
          const msg = messagesRef.current[id];
          if (msg) {
            const artifacts = detectArtifactsInText(msg.content, id);
            for (const artifact of artifacts) {
              actionsRef.current.registerArtifact(artifact);
              actionsRef.current.linkArtifactToMessage(id, artifact.id);
            }
          }
          actionsRef.current.completeAssistantMessage(id);
          _currentAssistantId = null;
        },

        onError: (errorMsg) => {
          const id = _currentAssistantId;
          if (id) {
            actionsRef.current.failAssistantMessage(id, errorMsg);
            _currentAssistantId = null;
          }
          toast.error("Agent error", { description: errorMsg });
        },

        // TICKET-012: inject a transient status token into the assistant message
        // so the user sees which tool is running during the silent pre-token gap.
        // Only injected when the message is still empty (no real tokens yet) to
        // avoid interrupting mid-stream content.
        onToolStart: (tool: string) => {
          if (_currentAssistantId) {
            const currentMsg = messagesRef.current[_currentAssistantId];
            if (currentMsg && currentMsg.content.length === 0) {
              actionsRef.current.appendAssistantToken(
                _currentAssistantId,
                `*Running ${tool}…*\n\n`,
              );
            }
          }
        },

        // onToolEnd is a no-op in the hook: real token content naturally
        // supersedes the activity line as the stream continues.
        onToolEnd: (_tool: string) => {
          // No-op: real token content supersedes the activity line.
        },
      });

      _client = client;
      client.connect();
    }

    return () => {
      _mountCount--;
      // Tear down only when the last consumer unmounts.
      if (_mountCount === 0 && _client) {
        _client.disconnect();
        _client = null;
      }
    };
  // Intentionally empty dep array: the effect runs exactly once per
  // mount/unmount cycle. Store actions are accessed via actionsRef.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function sendMessage(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;

    let convId = activeConvRef.current;
    if (!convId) {
      convId = actionsRef.current.createConversation();
    }

    actionsRef.current.appendUserMessage(convId, trimmed);
    const assistantId = actionsRef.current.beginAssistantMessage(convId);
    _currentAssistantId = assistantId;
    _client?.send(trimmed);
  }

  return { sendMessage, connectionStatus: connection };
}

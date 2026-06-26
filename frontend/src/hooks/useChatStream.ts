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
  const setConversationThreadId = useAppStore((s) => s.setConversationThreadId);
  const messages = useAppStore((s) => s.messages);
  const conversations = useAppStore((s) => s.conversations);

  // Mutable refs so WebSocket callbacks always see the latest state values
  // without needing to be recreated when state changes.
  const activeConvRef = useRef(activeConversationId);
  const messagesRef = useRef(messages);
  const conversationsRef = useRef(conversations);
  activeConvRef.current = activeConversationId;
  messagesRef.current = messages;
  conversationsRef.current = conversations;

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
    setConversationThreadId,
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
    setConversationThreadId,
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

        // TICKET-1.3: subagent lifecycle and token callbacks.
        // Mirror the onToolStart pattern: inject a status line only while the
        // message is still empty so we don't interrupt mid-stream content.
        // TODO(future): render subagent activity in a dedicated sub-region
        // (subagent-cards pattern) rather than appending to the main message.
        onSubagentStart: (name: string) => {
          if (_currentAssistantId) {
            const currentMsg = messagesRef.current[_currentAssistantId];
            if (currentMsg && currentMsg.content.length === 0) {
              actionsRef.current.appendAssistantToken(
                _currentAssistantId,
                `*Delegating to ${name}…*\n\n`,
              );
            }
          }
        },

        // Append streamed subagent text so the user sees motion during the
        // delegation window instead of a frozen "Thinking…" state.
        onSubagentToken: (_ns: string, text: string) => {
          if (_currentAssistantId) {
            actionsRef.current.appendAssistantToken(_currentAssistantId, text);
          }
        },

        // No-op: main-agent tokens that follow naturally supersede the
        // delegation status line once the subagent completes.
        onSubagentEnd: (_name: string) => {
          // No-op.
        },

        // TICKET-4.1: store the server-generated thread_id on the conversation
        // so every subsequent turn in this conversation resumes the same
        // LangGraph checkpoint state.
        onThreadId: (threadId: string) => {
          const convId = activeConvRef.current;
          if (convId && threadId) {
            actionsRef.current.setConversationThreadId(convId, threadId);
          }
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

    // Send the durable thread_id if this conversation already has one (i.e.
    // any prior turn received a "thread" frame).  Absent on the very first
    // turn — the server will generate an id and echo it back via onThreadId.
    const conversation = conversationsRef.current[convId];
    _client?.send(trimmed, conversation?.threadId);
  }

  return { sendMessage, connectionStatus: connection };
}

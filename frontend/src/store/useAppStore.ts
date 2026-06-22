import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type { GlobalAppState, Conversation, ChatMessage, Artifact, Report, ConnectionStatus, WorkspaceTab } from "@/types";
import { newId } from "@/lib/uuid";
import { mockUser, mockConversations, mockMessages, mockArtifacts, mockReports } from "@/data/mockData";
import { saveSnapshot, loadSnapshot } from "@/lib/persistence";

function toRecord<T extends { id: string }>(arr: T[]): Record<string, T> {
  return arr.reduce<Record<string, T>>((acc, item) => { acc[item.id] = item; return acc; }, {});
}

export const useAppStore = create<GlobalAppState>()(
  subscribeWithSelector((set) => ({
    conversations: toRecord(mockConversations),
    messages: toRecord(mockMessages),
    artifacts: toRecord(mockArtifacts),
    reports: toRecord(mockReports),
    user: mockUser,
    activeConversationId: "c_1",
    connection: "disconnected" as ConnectionStatus,
    workspace: { isOpen: false, activeTab: "artifacts" as const, selectedArtifactId: null, selectedReportId: null },
    isHistorySidebarOpen: true,
    composerValue: "",
    isAwaitingResponse: false,

    createConversation: () => {
      const id = newId();
      const now = Date.now();
      const conversation: Conversation = { id, title: "New chat", createdAt: now, updatedAt: now, messageIds: [] };
      set((s) => ({ conversations: { ...s.conversations, [id]: conversation }, activeConversationId: id }));
      return id;
    },

    selectConversation: (conversationId) => set({ activeConversationId: conversationId }),

    deleteConversation: (conversationId) => set((s) => {
      const next = { ...s.conversations };
      delete next[conversationId];
      const remaining = Object.values(next).sort((a, b) => b.updatedAt - a.updatedAt);
      const nextActive = s.activeConversationId === conversationId ? (remaining[0]?.id ?? null) : s.activeConversationId;
      return { conversations: next, activeConversationId: nextActive };
    }),

    appendUserMessage: (conversationId, content) => {
      const id = newId();
      const now = Date.now();
      const message: ChatMessage = { id, role: "user", content, status: "complete", createdAt: now, artifactIds: [], errorText: null };
      set((s) => {
        const conversation = s.conversations[conversationId];
        if (!conversation) return s;
        const isFirst = conversation.title === "New chat" && conversation.messageIds.length === 0;
        const title = isFirst ? content.slice(0, 40) + (content.length > 40 ? "…" : "") : conversation.title;
        return {
          messages: { ...s.messages, [id]: message },
          conversations: { ...s.conversations, [conversationId]: { ...conversation, title, updatedAt: now, messageIds: [...conversation.messageIds, id] } },
        };
      });
      return id;
    },

    beginAssistantMessage: (conversationId) => {
      const id = newId();
      const now = Date.now();
      const message: ChatMessage = { id, role: "assistant", content: "", status: "streaming", createdAt: now, artifactIds: [], errorText: null };
      set((s) => {
        const conversation = s.conversations[conversationId];
        if (!conversation) return { ...s, isAwaitingResponse: true };
        return {
          messages: { ...s.messages, [id]: message },
          conversations: { ...s.conversations, [conversationId]: { ...conversation, updatedAt: now, messageIds: [...conversation.messageIds, id] } },
          isAwaitingResponse: true,
        };
      });
      return id;
    },

    appendAssistantToken: (messageId, token) => set((s) => {
      const msg = s.messages[messageId];
      if (!msg) return s;
      return { messages: { ...s.messages, [messageId]: { ...msg, content: msg.content + token } } };
    }),

    completeAssistantMessage: (messageId) => set((s) => {
      const msg = s.messages[messageId];
      if (!msg) return s;
      return { messages: { ...s.messages, [messageId]: { ...msg, status: "complete" } }, isAwaitingResponse: false };
    }),

    failAssistantMessage: (messageId, errorText) => set((s) => {
      const msg = s.messages[messageId];
      if (!msg) return s;
      return { messages: { ...s.messages, [messageId]: { ...msg, status: "error", errorText } }, isAwaitingResponse: false };
    }),

    registerArtifact: (artifact: Artifact) => set((s) => {
      if (s.artifacts[artifact.id]) return s;
      return { artifacts: { ...s.artifacts, [artifact.id]: artifact } };
    }),

    linkArtifactToMessage: (messageId, artifactId) => set((s) => {
      const msg = s.messages[messageId];
      if (!msg || msg.artifactIds.includes(artifactId)) return s;
      return { messages: { ...s.messages, [messageId]: { ...msg, artifactIds: [...msg.artifactIds, artifactId] } } };
    }),

    registerReport: (report: Report) => set((s) => {
      if (s.reports[report.id]) return s;
      return { reports: { ...s.reports, [report.id]: report } };
    }),

    openArtifactInWorkspace: (artifactId) => set((s) => ({
      workspace: { ...s.workspace, isOpen: true, activeTab: "artifacts", selectedArtifactId: artifactId },
    })),

    openReportInWorkspace: (reportId) => set((s) => ({
      workspace: { ...s.workspace, isOpen: true, activeTab: "reports", selectedReportId: reportId },
    })),

    setWorkspaceTab: (tab: WorkspaceTab) => set((s) => ({ workspace: { ...s.workspace, activeTab: tab } })),
    closeWorkspace: () => set((s) => ({ workspace: { ...s.workspace, isOpen: false } })),
    toggleHistorySidebar: () => set((s) => ({ isHistorySidebarOpen: !s.isHistorySidebarOpen })),
    setComposerValue: (value) => set({ composerValue: value }),
    setConnection: (status: ConnectionStatus) => set({ connection: status }),
  }))
);

let saveTimer: ReturnType<typeof setTimeout> | null = null;
useAppStore.subscribe(
  (s) => [s.conversations, s.messages, s.artifacts, s.reports] as const,
  ([conversations, messages, artifacts, reports]) => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { saveSnapshot({ conversations, messages, artifacts, reports }); }, 800);
  }
);

loadSnapshot().then((snapshot) => {
  if (!snapshot) return;
  if (Object.keys(snapshot.conversations).length === 0) return;
  useAppStore.setState({
    conversations: snapshot.conversations,
    messages: snapshot.messages,
    artifacts: snapshot.artifacts,
    reports: snapshot.reports,
    activeConversationId: Object.values(snapshot.conversations).sort((a, b) => b.updatedAt - a.updatedAt)[0]?.id ?? null,
  });
});

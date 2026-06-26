export interface User {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
}

export type ArtifactKind = "chart_image" | "chart_interactive" | "table" | "file" | "link";

export interface ArtifactBase {
  id: string;
  kind: ArtifactKind;
  title: string;
  createdAt: number;
  messageId: string | null;
}

export interface ChartImageArtifact extends ArtifactBase {
  kind: "chart_image";
  url: string;
  filename: string;
}

export interface ChartInteractiveArtifact extends ArtifactBase {
  kind: "chart_interactive";
  url: string;
  filename: string;
}

export interface TableArtifact extends ArtifactBase {
  kind: "table";
  columns: string[];
  rows: Array<Array<string | number | null>>;
}

export interface FileArtifact extends ArtifactBase {
  kind: "file";
  url: string;
  filename: string;
  mimeType: string;
  sizeBytes: number | null;
}

export interface LinkArtifact extends ArtifactBase {
  kind: "link";
  href: string;
  faviconUrl: string | null;
}

export type Artifact =
  | ChartImageArtifact
  | ChartInteractiveArtifact
  | TableArtifact
  | FileArtifact
  | LinkArtifact;

export interface Report {
  id: string;
  title: string;
  filename: string;
  url: string;
  format: "html" | "pdf";
  createdAt: number;
}

export type MessageRole = "user" | "assistant" | "system";
export type MessageStatus = "pending" | "streaming" | "complete" | "error";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  createdAt: number;
  artifactIds: string[];
  errorText: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageIds: string[];
  // Durable LangGraph conversation identity.  Absent until the first server
  // response (the "thread" frame echoes the id it generated or accepted).
  // Once set, sent with every subsequent turn so the checkpointer resumes
  // the correct conversation state.  Distinct from session_id (ephemeral).
  threadId?: string;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type WorkspaceTab = "reports" | "artifacts";

export interface WorkspaceState {
  isOpen: boolean;
  activeTab: WorkspaceTab;
  selectedArtifactId: string | null;
  selectedReportId: string | null;
}

export interface BackendFileListItem {
  name: string;
  url: string;
}

export interface BackendHealth {
  status: string;
  model: string;
  fs_backend: string;
}

export interface WsDoneFrame {
  done: true;
}
export interface WsErrorFrame {
  error: string;
}
export type WsControlFrame = WsDoneFrame | WsErrorFrame;

export interface GlobalAppState {
  conversations: Record<string, Conversation>;
  messages: Record<string, ChatMessage>;
  artifacts: Record<string, Artifact>;
  reports: Record<string, Report>;
  user: User;
  activeConversationId: string | null;
  connection: ConnectionStatus;
  workspace: WorkspaceState;
  isHistorySidebarOpen: boolean;
  composerValue: string;
  isAwaitingResponse: boolean;
  createConversation: () => string;
  selectConversation: (conversationId: string) => void;
  deleteConversation: (conversationId: string) => void;
  appendUserMessage: (conversationId: string, content: string) => string;
  beginAssistantMessage: (conversationId: string) => string;
  appendAssistantToken: (messageId: string, token: string) => void;
  completeAssistantMessage: (messageId: string) => void;
  failAssistantMessage: (messageId: string, errorText: string) => void;
  registerArtifact: (artifact: Artifact) => void;
  linkArtifactToMessage: (messageId: string, artifactId: string) => void;
  registerReport: (report: Report) => void;
  openArtifactInWorkspace: (artifactId: string) => void;
  openReportInWorkspace: (reportId: string) => void;
  setWorkspaceTab: (tab: WorkspaceTab) => void;
  closeWorkspace: () => void;
  toggleHistorySidebar: () => void;
  setComposerValue: (value: string) => void;
  setConnection: (status: ConnectionStatus) => void;
  setConversationThreadId: (conversationId: string, threadId: string) => void;
}

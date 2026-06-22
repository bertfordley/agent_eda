import { get, set } from "idb-keyval";
import type { GlobalAppState, Artifact, Report, Conversation, ChatMessage } from "@/types";

const STORAGE_KEY = "eda-agent-state-v1";

interface PersistedSnapshot {
  conversations: Record<string, Conversation>;
  messages: Record<string, ChatMessage>;
  artifacts: Record<string, Artifact>;
  reports: Record<string, Report>;
}

export async function saveSnapshot(
  state: Pick<GlobalAppState, "conversations" | "messages" | "artifacts" | "reports">
): Promise<void> {
  await set(STORAGE_KEY, {
    conversations: state.conversations,
    messages: state.messages,
    artifacts: state.artifacts,
    reports: state.reports,
  });
}

export async function loadSnapshot(): Promise<PersistedSnapshot | null> {
  try {
    const data = await get<PersistedSnapshot>(STORAGE_KEY);
    return data ?? null;
  } catch {
    return null;
  }
}

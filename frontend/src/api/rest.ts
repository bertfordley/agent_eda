import { API_BASE_URL } from "@/lib/config";
import type { BackendHealth, BackendFileListItem } from "@/types";

export async function fetchHealth(): Promise<BackendHealth> {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json() as Promise<BackendHealth>;
}

export async function fetchCharts(): Promise<BackendFileListItem[]> {
  const res = await fetch(`${API_BASE_URL}/charts`);
  if (!res.ok) throw new Error(`Failed to fetch charts: ${res.statusText}`);
  return res.json() as Promise<BackendFileListItem[]>;
}

export async function fetchReports(): Promise<BackendFileListItem[]> {
  const res = await fetch(`${API_BASE_URL}/reports`);
  if (!res.ok) throw new Error(`Failed to fetch reports: ${res.statusText}`);
  return res.json() as Promise<BackendFileListItem[]>;
}

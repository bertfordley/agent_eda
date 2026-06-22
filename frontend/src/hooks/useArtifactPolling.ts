import { useEffect, useRef } from "react";
import { useAppStore } from "@/store/useAppStore";
import { fetchCharts, fetchReports } from "@/api/rest";
import { toAbsoluteUrl } from "@/lib/config";
import { newId } from "@/lib/uuid";
import type { ChartImageArtifact, ChartInteractiveArtifact, Report } from "@/types";

const POLL_INTERVAL_MS = 4000;

export function useArtifactPolling(): void {
  const registerArtifact = useAppStore((s) => s.registerArtifact);
  const registerReport = useAppStore((s) => s.registerReport);
  const artifacts = useAppStore((s) => s.artifacts);
  const reports = useAppStore((s) => s.reports);
  const artifactsRef = useRef(artifacts);
  const reportsRef = useRef(reports);
  artifactsRef.current = artifacts;
  reportsRef.current = reports;

  useEffect(() => {
    async function poll(): Promise<void> {
      if (document.hidden) return;
      try {
        const charts = await fetchCharts();
        const existingFilenames = new Set(Object.values(artifactsRef.current).map((a) => "filename" in a ? a.filename : ""));
        for (const item of charts) {
          const filename = item.name;
          if (existingFilenames.has(filename)) continue;
          const url = toAbsoluteUrl(item.url);
          const titleify = (f: string) => f.replace(/\.[^.]+$/, "").replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          if (filename.endsWith(".png")) {
            const artifact: ChartImageArtifact = { id: newId(), kind: "chart_image", title: titleify(filename), url, filename, createdAt: Date.now(), messageId: null };
            registerArtifact(artifact);
          } else if (filename.endsWith(".html")) {
            const artifact: ChartInteractiveArtifact = { id: newId(), kind: "chart_interactive", title: titleify(filename), url, filename, createdAt: Date.now(), messageId: null };
            registerArtifact(artifact);
          }
        }
      } catch { /* ignore */ }
      try {
        const reportItems = await fetchReports();
        const existingFilenames = new Set(Object.values(reportsRef.current).map((r) => r.filename));
        for (const item of reportItems) {
          const filename = item.name;
          if (existingFilenames.has(filename)) continue;
          const url = toAbsoluteUrl(item.url);
          const format = filename.endsWith(".pdf") ? "pdf" : "html";
          const title = filename.replace(/\.(html|pdf)$/, "").replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          const report: Report = { id: newId(), title, filename, url, format, createdAt: Date.now() };
          registerReport(report);
        }
      } catch { /* ignore */ }
    }
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [registerArtifact, registerReport]);
}

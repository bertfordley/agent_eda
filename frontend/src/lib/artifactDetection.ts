import type { Artifact, ChartImageArtifact, ChartInteractiveArtifact, LinkArtifact } from "@/types";
import { newId } from "./uuid";
import { toAbsoluteUrl } from "./config";

function stemToTitle(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, "");
  return stem.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function detectArtifactsInText(text: string, messageId: string): Artifact[] {
  const results: Artifact[] = [];
  const seenUrls = new Set<string>();

  const pngRegex = /charts\/([\w-]+\.png)/g;
  let match: RegExpExecArray | null;
  while ((match = pngRegex.exec(text)) !== null) {
    const filename = match[1];
    const url = toAbsoluteUrl(`/charts/${filename}`);
    if (seenUrls.has(url)) continue;
    seenUrls.add(url);
    const artifact: ChartImageArtifact = {
      id: newId(), kind: "chart_image", title: stemToTitle(filename),
      createdAt: Date.now(), messageId, url, filename,
    };
    results.push(artifact);
  }

  const htmlChartRegex = /charts\/([\w-]+\.html)/g;
  while ((match = htmlChartRegex.exec(text)) !== null) {
    const filename = match[1];
    const url = toAbsoluteUrl(`/charts/${filename}`);
    if (seenUrls.has(url)) continue;
    seenUrls.add(url);
    const artifact: ChartInteractiveArtifact = {
      id: newId(), kind: "chart_interactive", title: stemToTitle(filename),
      createdAt: Date.now(), messageId, url, filename,
    };
    results.push(artifact);
  }

  const urlRegex = /https?:\/\/[^\s)>\]"]+/g;
  while ((match = urlRegex.exec(text)) !== null) {
    const href = match[0];
    if (seenUrls.has(href)) continue;
    if (/\/(charts|reports)\//.test(href)) continue;
    seenUrls.add(href);
    let faviconUrl: string | null = null;
    try {
      const hostname = new URL(href).hostname;
      faviconUrl = `https://www.google.com/s2/favicons?domain=${hostname}`;
    } catch { /* ignore */ }
    const artifact: LinkArtifact = {
      id: newId(), kind: "link",
      title: href.length > 40 ? href.slice(0, 40) + "…" : href,
      createdAt: Date.now(), messageId, href, faviconUrl,
    };
    results.push(artifact);
  }

  return results;
}

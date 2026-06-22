import { useState, useRef } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import { useAppStore } from "@/store/useAppStore";
import { newId } from "@/lib/uuid";
import { cn } from "@/lib/cn";
import type { FileArtifact } from "@/types";

interface DropZoneProps {
  children: React.ReactNode;
}

export function DropZone({ children }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  // Track enter/leave events from nested elements using a counter so that
  // dragleave from a child doesn't prematurely hide the overlay.
  const dragDepthRef = useRef(0);
  const registerArtifact = useAppStore((s) => s.registerArtifact);

  function handleDragEnter(e: React.DragEvent) {
    e.preventDefault();
    dragDepthRef.current++;
    if (dragDepthRef.current === 1) setIsDragging(true);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    // Ensure the browser shows the "copy" drop cursor.
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave() {
    dragDepthRef.current--;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setIsDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      // NOTE: The current backend has no /upload endpoint.
      // Files are registered as local FileArtifacts and made available in the
      // workspace for preview. This is the forward-compatible seam for a future
      // backend upload route — when that route exists, POST the file here and
      // replace the blob URL with the returned server URL.
      const artifact: FileArtifact = {
        id: newId(),
        kind: "file",
        title: file.name,
        url: URL.createObjectURL(file),
        filename: file.name,
        mimeType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        createdAt: Date.now(),
        messageId: null,
      };
      registerArtifact(artifact);
      toast.info(`Attached ${file.name}`, {
        description: "Available in the Artifacts panel.",
      });
    }
  }

  return (
    <div
      className="relative flex flex-col"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}

      {/* Drop overlay — shown while a drag is in progress */}
      {isDragging && (
        <div
          className={cn(
            "absolute inset-0 z-20 flex items-center justify-center",
            "rounded-lg border-2 border-dashed border-primary",
            "bg-primary/5 backdrop-blur-sm"
          )}
          aria-hidden="true"
        >
          <div className="flex flex-col items-center gap-2 text-primary pointer-events-none">
            <Upload className="h-8 w-8" />
            <p className="text-sm font-medium">Drop files to attach</p>
          </div>
        </div>
      )}
    </div>
  );
}

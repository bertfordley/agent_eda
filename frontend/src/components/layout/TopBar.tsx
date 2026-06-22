import { useEffect, useState } from "react";
import { Sparkles, Menu, Settings } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { ConnectionBadge } from "./ConnectionBadge";
import { IconButton } from "@/components/common/IconButton";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { fetchHealth } from "@/api/rest";

export function TopBar() {
  const toggleHistorySidebar = useAppStore((s) => s.toggleHistorySidebar);
  const isHistorySidebarOpen = useAppStore((s) => s.isHistorySidebarOpen);
  const [model, setModel] = useState("gemini-2.0-flash");

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        if (h.model) setModel(h.model);
      })
      .catch(() => {
        // Keep the fallback model label if the backend is not yet reachable.
      });
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4 z-20">
      <div className="flex items-center gap-2">
        <IconButton
          icon={Menu}
          label={isHistorySidebarOpen ? "Close history sidebar" : "Open history sidebar"}
          onClick={toggleHistorySidebar}
        />
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          <span className="text-sm font-semibold tracking-tight">EDA Agent</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <ConnectionBadge />
        <Badge variant="secondary" className="font-mono text-[11px]">
          {model}
        </Badge>
        <DropdownMenu
          trigger={<IconButton icon={Settings} label="Settings" />}
          align="right"
        >
          <DropdownMenuItem disabled>Preferences</DropdownMenuItem>
          <DropdownMenuItem disabled>Keyboard shortcuts</DropdownMenuItem>
          <DropdownMenuItem disabled>About</DropdownMenuItem>
        </DropdownMenu>
      </div>
    </header>
  );
}

import { Plus } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ConversationGroup } from "./ConversationGroup";
import { HistoryEmptyState } from "./HistoryEmptyState";
import { UserFooter } from "./UserFooter";
import { dateGroupLabel, type DateGroupLabel } from "@/lib/time";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import type { Conversation } from "@/types";

const GROUP_ORDER: DateGroupLabel[] = ["Today", "Yesterday", "This Week", "Older"];

const SPRING = { type: "spring", damping: 30, stiffness: 300 } as const;

export function HistorySidebar() {
  const conversations = useAppStore((s) => s.conversations);
  const isOpen = useAppStore((s) => s.isHistorySidebarOpen);
  const createConversation = useAppStore((s) => s.createConversation);
  const toggleHistorySidebar = useAppStore((s) => s.toggleHistorySidebar);
  const isDesktop = useIsDesktop();

  // Sort by most-recently-updated and partition into date groups.
  const sorted = Object.values(conversations).sort((a, b) => b.updatedAt - a.updatedAt);
  const grouped = GROUP_ORDER.reduce<Record<DateGroupLabel, Conversation[]>>(
    (acc, label) => { acc[label] = []; return acc; },
    { Today: [], Yesterday: [], "This Week": [], Older: [] }
  );
  for (const conv of sorted) {
    grouped[dateGroupLabel(conv.updatedAt)].push(conv);
  }

  const sidebarContent = (
    <div className="flex h-full w-[280px] shrink-0 flex-col border-r border-border bg-card">
      <div className="p-3">
        <Button
          onClick={() => createConversation()}
          variant="outline"
          className="w-full justify-start gap-2"
          size="sm"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New chat
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0 px-2">
        {sorted.length === 0 ? (
          <HistoryEmptyState />
        ) : (
          <div className="py-1">
            {GROUP_ORDER.filter((g) => grouped[g].length > 0).map((label) => (
              <ConversationGroup
                key={label}
                label={label}
                conversations={grouped[label]}
              />
            ))}
          </div>
        )}
      </ScrollArea>

      <UserFooter />
    </div>
  );

  if (!isDesktop) {
    // Mobile: overlay drawer that slides in from the left over the chat.
    return (
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              key="sidebar-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-30 bg-background/60 backdrop-blur-sm"
              onClick={toggleHistorySidebar}
              aria-hidden="true"
            />
            <motion.div
              key="sidebar-panel"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={SPRING}
              className="fixed inset-y-0 left-0 z-40"
            >
              {sidebarContent}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    );
  }

  // Desktop: inline panel that collapses its width when hidden.
  return (
    <AnimatePresence initial={false}>
      {isOpen && (
        <motion.div
          key="sidebar-desktop"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 280, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={SPRING}
          className="overflow-hidden shrink-0"
        >
          {sidebarContent}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

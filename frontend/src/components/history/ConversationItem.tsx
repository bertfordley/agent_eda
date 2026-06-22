import { MessageSquare, MoreHorizontal, Trash2 } from "lucide-react";
import type { Conversation } from "@/types";
import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/cn";
import { DropdownMenu, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { IconButton } from "@/components/common/IconButton";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
}

export function ConversationItem({ conversation, isActive }: ConversationItemProps) {
  const selectConversation = useAppStore((s) => s.selectConversation);
  const deleteConversation = useAppStore((s) => s.deleteConversation);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "group relative flex h-10 w-full items-center gap-2 rounded-md px-2",
        "cursor-pointer transition-colors select-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isActive
          ? "bg-muted border-l-2 border-primary"
          : "hover:bg-muted/50 border-l-2 border-transparent"
      )}
      onClick={() => selectConversation(conversation.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectConversation(conversation.id);
        }
      }}
    >
      <MessageSquare
        className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
      <span className="flex-1 truncate text-sm">{conversation.title}</span>

      <div
        className="opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        <DropdownMenu
          trigger={<IconButton icon={MoreHorizontal} label="Conversation options" />}
          align="right"
        >
          <DropdownMenuItem
            onClick={() => deleteConversation(conversation.id)}
            className="text-destructive hover:bg-destructive/10"
          >
            <span className="flex items-center gap-2">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Delete
            </span>
          </DropdownMenuItem>
        </DropdownMenu>
      </div>
    </div>
  );
}

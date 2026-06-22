import { LogOut } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { Avatar } from "@/components/ui/avatar";
import { IconButton } from "@/components/common/IconButton";

export function UserFooter() {
  const user = useAppStore((s) => s.user);
  const initials = user.displayName.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className="flex items-center gap-2 border-t border-border p-3">
      <Avatar initials={initials} size="sm" />
      <span className="flex-1 truncate text-xs text-muted-foreground">{user.email}</span>
      <IconButton icon={LogOut} label="Sign out" disabled />
    </div>
  );
}

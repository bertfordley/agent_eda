import { cn } from "@/lib/cn";

interface AvatarProps {
  src?: string | null;
  alt?: string;
  initials?: string;
  className?: string;
  size?: "sm" | "md";
}

export function Avatar({ src, alt, initials, className, size = "md" }: AvatarProps) {
  const sizeClass = size === "sm" ? "h-6 w-6 text-xs" : "h-8 w-8 text-sm";
  return (
    <div className={cn("relative flex shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary font-medium", sizeClass, className)}>
      {src ? <img src={src} alt={alt ?? ""} className="h-full w-full rounded-full object-cover" /> : <span>{initials ?? "?"}</span>}
    </div>
  );
}

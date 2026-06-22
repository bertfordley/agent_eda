import * as React from "react";
import { cn } from "@/lib/cn";

interface TabsContextValue { value: string; onValueChange: (v: string) => void; }
const TabsContext = React.createContext<TabsContextValue>({ value: "", onValueChange: () => {} });

interface TabsProps { value: string; onValueChange: (v: string) => void; children: React.ReactNode; className?: string; }
export function Tabs({ value, onValueChange, children, className }: TabsProps) {
  return <TabsContext.Provider value={{ value, onValueChange }}><div className={cn("flex flex-col", className)}>{children}</div></TabsContext.Provider>;
}

export function TabsList({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("inline-flex h-9 items-center rounded-md bg-muted p-1 text-muted-foreground", className)}>{children}</div>;
}

export function TabsTrigger({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) {
  const ctx = React.useContext(TabsContext);
  const active = ctx.value === value;
  return (
    <button onClick={() => ctx.onValueChange(value)}
      className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-card text-foreground shadow-sm" : "hover:bg-muted-foreground/10 hover:text-foreground", className)}>
      {children}
    </button>
  );
}

export function TabsContent({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) {
  const ctx = React.useContext(TabsContext);
  if (ctx.value !== value) return null;
  return <div className={cn("flex-1 min-h-0", className)}>{children}</div>;
}

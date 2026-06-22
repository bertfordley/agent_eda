import { Database, Table, BarChart3, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

const prompts = [
  { icon: Database, text: "List my BigQuery datasets" },
  { icon: Table, text: "Describe the schema of reporting.orders" },
  { icon: BarChart3, text: "Show Q2 revenue by region as a bar chart" },
  { icon: FileText, text: "Build an HTML report of monthly trends" },
];

interface SuggestedPromptsProps {
  onPick: (prompt: string) => void;
}

export function SuggestedPrompts({ onPick }: SuggestedPromptsProps) {
  return (
    <div className="grid grid-cols-2 gap-2 w-full max-w-md">
      {prompts.map(({ icon: Icon, text }) => (
        <Button
          key={text}
          variant="outline"
          size="sm"
          onClick={() => onPick(text)}
          className="justify-start gap-2 h-auto py-2.5 px-3 text-left whitespace-normal"
        >
          <Icon className="h-4 w-4 shrink-0 text-primary" />
          <span className="text-xs leading-tight">{text}</span>
        </Button>
      ))}
    </div>
  );
}

import type { TableArtifact } from "@/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/cn";

interface TableRendererProps {
  artifact: TableArtifact;
}

function formatCell(value: string | number | null): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function isNumericCell(value: string | number | null): boolean {
  return typeof value === "number";
}

export function TableRenderer({ artifact }: TableRendererProps) {
  const rowCount = artifact.rows.length;

  return (
    <div className="flex flex-col h-full">
      {/* Table title bar */}
      <div className="border-b border-border px-3 py-2 shrink-0">
        <p className="text-sm font-medium">{artifact.title}</p>
      </div>

      {/* Scrollable table body */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3">
          <div className="rounded-md border border-border overflow-hidden">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  {artifact.columns.map((col, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="border-b border-border bg-muted px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {artifact.rows.map((row, ri) => (
                  <tr
                    key={ri}
                    className={ri % 2 === 0 ? "bg-transparent" : "bg-muted/20"}
                  >
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className={cn(
                          "border-b border-border/30 px-3 py-2 whitespace-nowrap",
                          isNumericCell(cell)
                            ? "text-right tabular-nums"
                            : "text-left"
                        )}
                      >
                        {cell === null ? (
                          <span className="text-muted-foreground/50">—</span>
                        ) : (
                          formatCell(cell)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-2 text-xs text-muted-foreground px-1">
            {rowCount} {rowCount === 1 ? "row" : "rows"}
          </p>
        </div>
      </ScrollArea>
    </div>
  );
}

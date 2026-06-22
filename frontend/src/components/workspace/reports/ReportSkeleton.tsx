import { Skeleton } from "@/components/ui/skeleton";

export function ReportSkeleton() {
  return (
    <div className="flex flex-col gap-3 p-4">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-[90%]" />
      <Skeleton className="h-3 w-[85%]" />
      <div className="mt-4 space-y-2">
        <Skeleton className="h-32 w-full rounded-md" />
        <Skeleton className="h-3 w-[70%]" />
        <Skeleton className="h-3 w-[80%]" />
        <Skeleton className="h-3 w-[60%]" />
      </div>
    </div>
  );
}

import { Skeleton } from "@/components/ui/skeleton";

export function ArtifactSkeleton() {
  return (
    <div className="flex flex-col gap-3 p-4">
      <Skeleton className="h-48 w-full rounded-md" />
      <Skeleton className="h-3 w-40" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

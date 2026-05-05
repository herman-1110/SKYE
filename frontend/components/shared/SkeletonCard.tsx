export default function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={`rounded-lg bg-s-surface border border-s-border overflow-hidden ${className}`}>
      <div className="p-4 space-y-3">
        <div className="skeleton h-3 w-1/3 rounded" />
        <div className="skeleton h-6 w-1/2 rounded" />
        <div className="skeleton h-3 w-2/3 rounded" />
      </div>
    </div>
  );
}

export function SkeletonRow({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg bg-s-surface border border-s-border ${className}`}>
      <div className="skeleton h-8 w-8 rounded-full shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="skeleton h-3 w-2/3 rounded" />
        <div className="skeleton h-2 w-1/3 rounded" />
      </div>
    </div>
  );
}

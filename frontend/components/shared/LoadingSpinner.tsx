export default function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sz = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" }[size];
  return (
    <div className="flex items-center justify-center p-8" role="status" aria-label="Loading">
      <div className={`${sz} animate-spin rounded-full border-2 border-s-border border-t-s-accent`} />
    </div>
  );
}

export function FullScreenLoader() {
  return (
    <div className="fixed inset-0 bg-s-base flex items-center justify-center z-50">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-s-border border-t-s-accent" />
        <span className="font-mono text-xs text-s-muted tracking-widest uppercase">Authenticating</span>
      </div>
    </div>
  );
}

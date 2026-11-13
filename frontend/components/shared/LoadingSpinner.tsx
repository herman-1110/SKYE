export default function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sz = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" }[size];
  return (
    <div className="flex items-center justify-center p-8" role="status" aria-label="Loading">
      <div className={`${sz} animate-spin rounded-full border-2 border-s-border border-t-s-accent`} />
    </div>
  );
}

// The AUTHENTICATING screen the dashboard shows until the sign-in check is
// done. data-skye-loader lets the load watchdog in app/layout.tsx see that
// it's still up. The hint under it appears only after 25 s (pure CSS, see
// .skye-slow-hint in globals.css), so it also shows when the page's
// JavaScript never started; its link is a plain reload.
export function FullScreenLoader() {
  return (
    <div data-skye-loader="" className="fixed inset-0 bg-s-base flex items-center justify-center z-50">
      <div className="relative flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-s-border border-t-s-accent" />
        <span className="font-mono text-xs text-s-muted tracking-widest uppercase">Authenticating</span>
        <div className="skye-slow-hint absolute top-full left-1/2 -translate-x-1/2 mt-6 w-64 text-center space-y-2">
          <p className="text-xs text-s-muted">This is taking longer than it should.</p>
          <a href="" className="inline-block text-xs font-medium text-s-accent hover:underline">
            Reload the page
          </a>
        </div>
      </div>
    </div>
  );
}

// Shown instead of the dashboard when the sign-in check fails, so the user
// sees why and can try again instead of watching AUTHENTICATING forever.
export function FullScreenError({
  message,
  onRetry,
  onSignOut,
}: {
  message: string;
  onRetry: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-s-base flex items-center justify-center z-50 px-4">
      <div
        role="alert"
        className="max-w-sm w-full bg-s-surface border border-s-danger/40 rounded-xl p-8 text-center space-y-4"
      >
        <div>
          <h1 className="text-lg font-bold text-s-danger">Can&apos;t open the dashboard</h1>
          <p className="text-sm text-s-muted mt-1">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="w-full py-2.5 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 transition-opacity"
        >
          Retry
        </button>
        <button
          type="button"
          onClick={onSignOut}
          className="text-xs text-s-muted hover:text-s-text transition-colors font-mono"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

"use client";
import { useEffect, useRef } from "react";
import { useToastStore, type Toast, type ToastType } from "@/store/toastStore";

const DISMISS_MS = 4000;

function CheckIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2 6 5 9 10 3"/>
    </svg>
  );
}

function XIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="2" y1="2" x2="10" y2="10"/><line x1="10" y1="2" x2="2" y2="10"/>
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="5.5" x2="6" y2="9.5"/><circle cx="6" cy="3" r="0.5" fill="currentColor" stroke="none"/>
    </svg>
  );
}

const ICON_CONFIG: Record<ToastType, { bg: string; text: string; icon: React.ReactNode }> = {
  success: { bg: "bg-emerald-500/20", text: "text-emerald-400",  icon: <CheckIcon /> },
  error:   { bg: "bg-red-500/20",     text: "text-red-400",      icon: <XIcon /> },
  info:    { bg: "bg-amber-500/20",   text: "text-amber-400",    icon: <InfoIcon /> },
};

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { bg, text, icon } = ICON_CONFIG[toast.type];

  const startTimer = () => {
    timerRef.current = setTimeout(() => onRemove(toast.id), DISMISS_MS);
  };
  const clearTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  };

  useEffect(() => {
    startTimer();
    return clearTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      onMouseEnter={clearTimer}
      onMouseLeave={startTimer}
      className="animate-toast-in pointer-events-auto flex items-center gap-3 px-4 py-3.5 rounded-xl min-w-[300px] max-w-sm group"
      style={{
        background: "var(--glass-bg)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        border: "1px solid var(--glass-border)",
        boxShadow: "var(--glass-shadow)",
      }}
    >
      {/* Type icon */}
      <span className={`h-5 w-5 rounded-full flex items-center justify-center shrink-0 ${bg} ${text}`}>
        {icon}
      </span>

      {/* Message */}
      <p className="text-sm text-s-text flex-1 leading-snug">{toast.message}</p>

      {/* Close — visible on hover */}
      <button
        onClick={() => onRemove(toast.id)}
        className="shrink-0 text-s-muted hover:text-s-text transition-colors opacity-0 group-hover:opacity-100"
        aria-label="Dismiss"
      >
        <XIcon size={12} />
      </button>
    </div>
  );
}

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={removeToast} />
      ))}
    </div>
  );
}

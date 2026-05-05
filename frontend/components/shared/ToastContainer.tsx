"use client";
import { useToastStore, type ToastType } from "@/store/toastStore";

const BORDER: Record<ToastType, string> = {
  success: "border-l-s-success",
  error:   "border-l-s-danger",
  info:    "border-l-s-accent",
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg
            bg-s-elevated border border-s-border border-l-2 ${BORDER[t.type]}
            shadow-xl animate-in slide-in-from-right-4 duration-200 min-w-[280px]`}
        >
          <p className="text-sm text-s-text flex-1">{t.message}</p>
          <button
            onClick={() => removeToast(t.id)}
            className="text-s-muted hover:text-s-text text-lg leading-none"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

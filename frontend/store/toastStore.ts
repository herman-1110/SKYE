import { create } from "zustand";

export type ToastType = "success" | "error" | "info";

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

const MAX_TOASTS = 3;

interface ToastState {
  toasts: Toast[];
  addToast: (message: string, type: ToastType) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type) => {
    const id = crypto.randomUUID();
    set((s) => {
      const next = [...s.toasts, { id, message, type }];
      // Drop oldest toasts beyond the cap
      return { toasts: next.slice(-MAX_TOASTS) };
    });
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const toast = {
  success: (msg: string) => useToastStore.getState().addToast(msg, "success"),
  error:   (msg: string) => useToastStore.getState().addToast(msg, "error"),
  info:    (msg: string) => useToastStore.getState().addToast(msg, "info"),
};

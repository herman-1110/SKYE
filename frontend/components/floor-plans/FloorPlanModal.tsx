"use client";
import { useEffect } from "react";
import type { User } from "firebase/auth";
import FloorPlanUpload from "./FloorPlanUpload";

interface Props {
  user: User;
  onClose: () => void;
}

export default function FloorPlanModal({ user, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md">
        <FloorPlanUpload
          user={user}
          onUploaded={onClose}
          onCancel={onClose}
        />
      </div>
    </div>
  );
}

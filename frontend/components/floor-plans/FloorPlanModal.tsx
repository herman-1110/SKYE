"use client";
import { useRef, useState } from "react";
import { uploadFloorPlan } from "@/services/floorPlanService";
import { toast } from "@/store/toastStore";

interface Props {
  userId: string;
  onClose: () => void;
}

export default function FloorPlanModal({ userId, onClose }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !name.trim()) return;
    setUploading(true);
    setProgress(30);
    try {
      setProgress(60);
      await uploadFloorPlan(file, name.trim(), userId);
      setProgress(100);
      toast.success("Floor plan uploaded successfully");
      onClose();
    } catch {
      toast.error("Upload failed. Please try again.");
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-s-elevated border border-s-border rounded-xl p-6 w-full max-w-md space-y-4 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-s-text">Upload Floor Plan</h2>
          <button onClick={onClose} className="text-s-muted hover:text-s-text text-xl leading-none">×</button>
        </div>

        <input
          type="text"
          placeholder='Name — e.g. "Level 1 — Warehouse A"'
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full bg-s-surface border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent"
        />

        {/* Drop zone */}
        <label className="block border-2 border-dashed border-s-border hover:border-s-accent rounded-lg p-8 text-center cursor-pointer transition-colors group">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,application/pdf" className="hidden" />
          <svg className="mx-auto mb-3 text-s-muted group-hover:text-s-accent transition-colors" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
            <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
          </svg>
          <p className="text-sm text-s-muted group-hover:text-s-text transition-colors">
            Click to browse or drag & drop
          </p>
          <p className="text-xs text-s-muted mt-1">PNG, JPG, PDF — max 10 MB</p>
        </label>

        {uploading && (
          <div className="h-1.5 bg-s-surface rounded-full overflow-hidden">
            <div
              className="h-full bg-s-accent rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-lg border border-s-border text-s-muted text-sm hover:bg-s-surface transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={uploading || !name.trim()}
            className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-semibold text-sm disabled:opacity-40 hover:opacity-90 transition-opacity"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}

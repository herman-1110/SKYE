"use client";
import { useRef, useState, useEffect } from "react";
import { uploadFloorPlan } from "@/services/floorPlanService";
import { toast } from "@/store/toastStore";
import type { User } from "firebase/auth";

interface Props {
  user: User;
  onUploaded: () => void;
  onCancel?: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function getTypeBadge(file: File): string {
  if (file.type === "image/png") return "PNG";
  if (file.type === "image/jpeg" || file.type === "image/jpg") return "JPG";
  if (file.type === "image/webp") return "WEBP";
  if (file.type === "application/pdf") return "PDF";
  return file.name.split(".").pop()?.toUpperCase() ?? "FILE";
}

const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"];

export default function FloorPlanUpload({ user, onUploaded, onCancel }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  const handleFileSelect = (file: File) => {
    if (!ACCEPTED.includes(file.type)) {
      setError("Invalid file type — PNG, JPG, WEBP, or PDF only.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large — maximum 10 MB.");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(file);
    setError(null);
    setPreviewUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : null);
  };

  const clearFile = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileRef.current) fileRef.current.value = "";
    setError(null);
  };

  const handleUpload = async () => {
    if (!selectedFile || !name.trim()) return;
    setError(null);
    setProgress(0);
    try {
      const token = await user.getIdToken();
      await uploadFloorPlan(selectedFile, name.trim(), user.uid, token, setProgress);
      setName("");
      clearFile();
      setProgress(null);
      toast.success("Floor plan uploaded successfully");
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
      setProgress(null);
    }
  };

  const uploading = progress !== null;

  return (
    <div className="rounded-xl p-5 space-y-4"
      style={{ background: "var(--glass-bg)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid var(--glass-border)", boxShadow: "var(--glass-shadow)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">Upload Floor Plan</h3>
        {onCancel && (
          <button onClick={onCancel} className="text-s-muted hover:text-s-text transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        )}
      </div>

      {/* Name */}
      <div className="space-y-1.5">
        <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Name</label>
        <input
          type="text"
          placeholder='e.g. "Level 1 — Warehouse A"'
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={uploading}
          className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors disabled:opacity-50"
        />
      </div>

      {/* File zone */}
      <div className="space-y-1.5">
        <label className="text-xs font-mono text-s-muted tracking-widest uppercase">File</label>

        {selectedFile ? (
          /* Preview card */
          <div className="border border-s-border rounded-lg overflow-hidden">
            {previewUrl ? (
              <img src={previewUrl} alt={selectedFile.name} className="w-full h-40 object-cover" />
            ) : (
              <div className="h-28 bg-s-elevated flex flex-col items-center justify-center gap-2 text-s-accent">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
                <span className="font-mono text-[10px] tracking-widest">PDF</span>
              </div>
            )}
            <div className="flex items-center justify-between px-3 py-2 bg-s-elevated border-t border-s-border">
              <div className="min-w-0">
                <p className="text-xs font-medium text-s-text truncate">{selectedFile.name}</p>
                <p className="font-mono text-[10px] text-s-muted tracking-wide mt-0.5">
                  {getTypeBadge(selectedFile)} · {formatBytes(selectedFile.size)}
                </p>
              </div>
              <button
                onClick={clearFile}
                disabled={uploading}
                className="ml-3 shrink-0 text-s-muted hover:text-s-danger transition-colors disabled:opacity-40"
                title="Remove file"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
        ) : (
          /* Drop zone */
          <div
            onClick={() => !uploading && fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); if (!uploading) setDragOver(true); }}
            onDragEnter={(e) => { e.preventDefault(); if (!uploading) setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (uploading) return;
              const f = e.dataTransfer.files[0];
              if (f) handleFileSelect(f);
            }}
            className={`flex flex-col items-center justify-center gap-2 w-full border border-dashed rounded-lg px-4 py-8 cursor-pointer transition-colors select-none
              ${uploading ? "opacity-50 pointer-events-none border-s-border" : dragOver ? "border-s-accent bg-s-accent/5" : "border-s-border hover:border-s-accent"}`}
          >
            <svg
              width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
              className={dragOver ? "text-s-accent" : "text-s-muted"}
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <div className="text-center pointer-events-none">
              <p className={`text-sm ${dragOver ? "text-s-accent" : "text-s-muted"}`}>
                {dragOver ? "Drop to add file" : "Click to browse or drag & drop"}
              </p>
              <p className="font-mono text-[10px] text-s-muted tracking-wide mt-0.5">PNG, JPG, PDF · Max 10 MB</p>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp,application/pdf"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }}
            />
          </div>
        )}
      </div>

      {/* Progress */}
      {progress !== null && (
        <div className="space-y-1.5">
          <div className="h-1.5 w-full bg-s-border rounded-full overflow-hidden">
            <div className="h-full bg-s-accent rounded-full transition-all duration-200" style={{ width: `${progress}%` }} />
          </div>
          <p className="font-mono text-[10px] text-s-muted tracking-widest">{progress}% UPLOADED</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 bg-s-danger/10 border border-s-danger/30 rounded-lg px-3 py-2">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-danger shrink-0 mt-0.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p className="text-s-danger text-xs">{error}</p>
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleUpload}
        disabled={uploading || !name.trim() || !selectedFile}
        className="w-full py-2.5 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-2"
      >
        {uploading && <span className="h-3.5 w-3.5 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
        {uploading ? "Uploading…" : "Upload Floor Plan"}
      </button>
    </div>
  );
}

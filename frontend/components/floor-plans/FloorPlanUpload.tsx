"use client";
import { useRef, useState } from "react";
import { uploadFloorPlan } from "@/services/floorPlanService";

interface Props {
  userId: string;
  onUploaded: () => void;
}

export default function FloorPlanUpload({ userId, onUploaded }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !name.trim()) return;
    setUploading(true);
    setError(null);
    try {
      await uploadFloorPlan(file, name.trim(), userId);
      setName("");
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch {
      setError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <h3 className="font-semibold text-sm">Upload New Floor Plan</h3>
      <input
        type="text"
        placeholder='Name (e.g. "Level 1 — Warehouse A")'
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full border rounded px-3 py-2 text-sm"
      />
      <input ref={fileRef} type="file" accept="image/*" className="text-sm" />
      {error && <p className="text-red-500 text-xs">{error}</p>}
      <button
        onClick={handleUpload}
        disabled={uploading || !name.trim()}
        className="bg-blue-600 text-white rounded px-4 py-2 text-sm disabled:opacity-50"
      >
        {uploading ? "Uploading…" : "Upload"}
      </button>
    </div>
  );
}

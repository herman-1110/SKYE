"use client";
import { useRouter } from "next/navigation";

export default function GenerateReportButton() {
  const router = useRouter();
  return (
    <button
      onClick={() => router.push("/dashboard/reports")}
      className="px-4 py-2 bg-s-accent text-s-base rounded-lg text-sm font-mono font-bold hover:opacity-90 transition-opacity"
    >
      Generate Audit Report
    </button>
  );
}

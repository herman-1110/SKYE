"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import SafetySettings from "@/components/dashboard/SafetySettings";

export default function SafetySettingsPage() {
  const { userRecord, isLoading } = useAuth();
  const router = useRouter();
  const isAdmin = userRecord?.role === "admin";

  useEffect(() => {
    if (!isLoading && !isAdmin) router.replace("/dashboard");
  }, [isLoading, isAdmin, router]);

  if (isLoading) return null;
  if (!isAdmin) return null;

  return (
    <div className="max-w-[1400px] mx-auto px-8 py-8">
      <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase mb-6">
        Safety Settings
      </h1>
      <SafetySettings />
    </div>
  );
}

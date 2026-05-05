"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { usePositions } from "@/hooks/usePositions";
import { useAlerts } from "@/hooks/useAlerts";
import Navbar from "@/components/layout/Navbar";
import Sidebar from "@/components/layout/Sidebar";
import ToastContainer from "@/components/shared/ToastContainer";
import { FullScreenLoader } from "@/components/shared/LoadingSpinner";

function DataSubscriptions() {
  usePositions();
  useAlerts();
  return null;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, userRecord, isLoading } = useAuth();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    if (!user) { router.push("/login"); return; }
    // Guards go to their own view, not the admin dashboard
    if (userRecord && userRecord.role !== "admin") router.push("/guard");
  }, [user, userRecord, isLoading, router]);

  if (isLoading) return <FullScreenLoader />;
  if (!user || (userRecord && userRecord.role !== "admin")) return null;

  const sidebarW = collapsed ? 60 : 240;

  return (
    <div className="min-h-screen bg-s-base">
      <DataSubscriptions />
      <Navbar user={user} />
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <main
        className="pt-14 min-h-screen transition-all duration-200"
        style={{ marginLeft: sidebarW }}
      >
        <div className="p-4">{children}</div>
      </main>
      <ToastContainer />
    </div>
  );
}

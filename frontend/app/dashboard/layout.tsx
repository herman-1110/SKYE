"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { usePositions } from "@/hooks/usePositions";
import { useAlerts } from "@/hooks/useAlerts";
import Navbar from "@/components/layout/Navbar";
import Sidebar from "@/components/layout/Sidebar";
import ToastContainer from "@/components/shared/ToastContainer";
import CriticalAlertBanner from "@/components/shared/CriticalAlertBanner";
import { FullScreenLoader } from "@/components/shared/LoadingSpinner";

function DataSubscriptions() {
  usePositions();
  useAlerts();
  return null;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, userRecord, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const hasLoadedOnce = useRef(false);

  // Mark auth as resolved so subsequent navigations skip the full-screen loader
  if (!isLoading) {
    hasLoadedOnce.current = true;
  }

  useEffect(() => {
    if (isLoading) return;
    if (!user) { router.push("/login"); return; }
    if (!userRecord) return;
    if (userRecord.status === "pending") { router.push("/pending-approval"); return; }
    if (userRecord.status === "suspended") { router.push("/suspended"); return; }
  }, [user, userRecord, isLoading, router]);

  // Only block on initial load — tab navigation never triggers this again
  if (isLoading && !hasLoadedOnce.current) return <FullScreenLoader />;
  if (!user) return null;
  if (userRecord && (userRecord.status === "pending" || userRecord.status === "suspended")) return null;

  const sidebarW = collapsed ? 60 : 240;

  return (
    <div className="min-h-screen bg-s-base">
      <DataSubscriptions />
      <Navbar user={user} />
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <main
        key={pathname}
        className="pt-14 min-h-screen transition-[margin-left] duration-200 animate-fade-in"
        style={{ marginLeft: sidebarW, overflowX: "hidden", position: "relative", willChange: "opacity" }}
      >
        <div className="p-4">{children}</div>
      </main>
      <CriticalAlertBanner />
      <ToastContainer />
    </div>
  );
}

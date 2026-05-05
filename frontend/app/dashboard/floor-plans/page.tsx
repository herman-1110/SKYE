"use client";
import { useEffect, useState } from "react";
import { subscribeToFloorPlans } from "@/services/floorPlanService";
import { useAuth } from "@/hooks/useAuth";
import FloorPlanUpload from "@/components/floor-plans/FloorPlanUpload";
import FloorPlanList from "@/components/floor-plans/FloorPlanList";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import type { FloorPlanRecord } from "@/types/floorPlan";

export default function FloorPlansPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [plans, setPlans] = useState<FloorPlanRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const unsubscribe = subscribeToFloorPlans(user.uid, (data) => {
      setPlans(data);
      setIsLoading(false);
    });
    return unsubscribe;
  }, [user]);

  if (authLoading || isLoading) return <LoadingSpinner />;
  if (!user) return <p className="p-4 text-sm text-gray-500">Not signed in.</p>;

  return (
    <main className="p-4 max-w-2xl mx-auto space-y-6">
      <h1 className="text-xl font-bold">Floor Plans</h1>
      <FloorPlanUpload userId={user.uid} onUploaded={() => {}} />
      <section>
        <h2 className="font-semibold mb-3 text-sm text-gray-600">Your Floor Plans</h2>
        <FloorPlanList plans={plans} userId={user.uid} />
      </section>
    </main>
  );
}

"use client";
import { useState } from "react";
import { activateFloorPlan, updateScale } from "@/services/floorPlanService";
import type { FloorPlanRecord } from "@/types/floorPlan";

interface Props {
  plans: FloorPlanRecord[];
  userId: string;
}

export default function FloorPlanList({ plans, userId }: Props) {
  const [scaleInputs, setScaleInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const handleActivate = async (id: string) => {
    setBusy(id);
    try {
      await activateFloorPlan(id, userId);
    } finally {
      setBusy(null);
    }
  };

  const handleScaleSave = async (id: string) => {
    const val = parseFloat(scaleInputs[id] ?? "");
    if (!val || val <= 0) return;
    setBusy(id + "-scale");
    try {
      await updateScale(id, val);
    } finally {
      setBusy(null);
    }
  };

  if (plans.length === 0) {
    return <p className="text-sm text-gray-500">No floor plans uploaded yet.</p>;
  }

  return (
    <ul className="space-y-3">
      {plans.map((plan) => (
        <li key={plan.floor_plan_id} className="bg-white rounded-xl border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium text-sm">{plan.name}</span>
            {plan.is_active && (
              <span className="text-xs bg-green-100 text-green-700 rounded-full px-2 py-0.5">
                Active
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400">{plan.uploaded_at}</p>

          {/* Scale calibration */}
          <div className="flex items-center gap-2">
            <input
              type="number"
              min="0.1"
              step="0.1"
              placeholder={plan.scale_pixels_per_meter?.toString() ?? "px / metre"}
              value={scaleInputs[plan.floor_plan_id] ?? ""}
              onChange={(e) =>
                setScaleInputs((prev) => ({ ...prev, [plan.floor_plan_id]: e.target.value }))
              }
              className="border rounded px-2 py-1 text-xs w-32"
            />
            <button
              onClick={() => handleScaleSave(plan.floor_plan_id)}
              disabled={busy === plan.floor_plan_id + "-scale"}
              className="text-xs bg-gray-100 hover:bg-gray-200 rounded px-2 py-1 disabled:opacity-50"
            >
              Set Scale
            </button>
          </div>

          {!plan.is_active && (
            <button
              onClick={() => handleActivate(plan.floor_plan_id)}
              disabled={busy === plan.floor_plan_id}
              className="text-xs bg-indigo-600 text-white rounded px-3 py-1 disabled:opacity-50"
            >
              {busy === plan.floor_plan_id ? "Activating…" : "Set as Active"}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

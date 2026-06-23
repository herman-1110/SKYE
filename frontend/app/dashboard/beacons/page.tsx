"use client";
import BeaconManager from "@/components/map/BeaconManager";

export default function BeaconsPage() {
  return (
    <div className="max-w-[1400px] mx-auto px-8 py-8">
      <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase mb-6">
        Beacon Registry
      </h1>
      <BeaconManager />
    </div>
  );
}

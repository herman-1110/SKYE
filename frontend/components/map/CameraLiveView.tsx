"use client";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { isAdminRole } from "@/types/user";
import { openCCTVLiveView, type ApiError, type CCTVRecord } from "@/services/floorService";

// Prompt 132: the live-video slot in CameraPanel. WebRTC with the signaling
// going through the backend (Herman's decision 6), video only (decision 7).
// The browser offers to receive one video track; the backend forwards the
// offer to go2rtc on the server and returns its answer, and the video then
// flows from go2rtc straight to this page. Admins only.
//
// One RTCPeerConnection per open panel, camera and quality. Closing the panel,
// switching camera or toggling HD closes it, so go2rtc stops pulling the
// camera's stream once it notices the viewer has gone.

type Quality = "sub" | "main";
type Phase = "connecting" | "live" | "offline" | "error";

const ICE_GATHER_CAP_MS = 2_000;   // the signaling is one request (no trickle), so gather first, briefly
const FIRST_FRAME_MS = 15_000;

function waitForIceGathering(pc: RTCPeerConnection, capMs: number): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", onChange);
      resolve();
    };
    const onChange = () => { if (pc.iceGatheringState === "complete") finish(); };
    const timer = setTimeout(finish, capMs);
    pc.addEventListener("icegatheringstatechange", onChange);
  });
}

interface Props {
  buildingId: string;
  cctv: CCTVRecord;
  online: boolean;   // the camera answered liveness in the last 10 s (useCCTVHeartbeats)
}

export default function CameraLiveView({ buildingId, cctv, online }: Props) {
  const { userRecord } = useAuth();
  const isAdmin = isAdminRole(userRecord?.role);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [quality, setQuality] = useState<Quality>("sub");
  const [phase, setPhase] = useState<Phase>("connecting");
  const [message, setMessage] = useState("Connecting…");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!isAdmin) return;
    if (!online) {
      setPhase("offline");
      setMessage("Camera offline");
      return;
    }
    let closed = false;
    const video = videoRef.current;
    const pc = new RTCPeerConnection({ iceServers: [] });
    const show = (p: Phase, text: string) => { if (!closed) { setPhase(p); setMessage(text); } };
    const firstFrame = setTimeout(() => show("error", "No video arrived from the camera."), FIRST_FRAME_MS);
    const onPlaying = () => { clearTimeout(firstFrame); show("live", ""); };

    show("connecting", "Connecting…");
    pc.addTransceiver("video", { direction: "recvonly" });   // no audio track is requested
    pc.ontrack = (e) => {
      if (closed || !video) return;
      video.srcObject = e.streams[0] ?? new MediaStream([e.track]);
      video.play().catch(() => { /* muted autoplay; "playing" below is what counts */ });
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed") {
        clearTimeout(firstFrame);
        show("error", "The video connection failed.");
      }
    };
    video?.addEventListener("playing", onPlaying);

    (async () => {
      await pc.setLocalDescription(await pc.createOffer());
      await waitForIceGathering(pc, ICE_GATHER_CAP_MS);
      if (closed || !pc.localDescription) return;
      const answer = await openCCTVLiveView(buildingId, cctv.floor_id, cctv.id, pc.localDescription.sdp, quality);
      if (closed) return;
      await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });
    })().catch((err: unknown) => {
      clearTimeout(firstFrame);
      const e = err as ApiError;
      // The backend's sentences are already plain ("Live view isn't running
      // on the server", ...); a 409 that says offline is shown as such.
      if (e?.status === 409 && /offline/i.test(e.message)) show("offline", "Camera offline");
      else show("error", e instanceof Error && e.message ? e.message : "Live view failed.");
    });

    return () => {
      closed = true;
      clearTimeout(firstFrame);
      video?.removeEventListener("playing", onPlaying);
      pc.ontrack = null;
      pc.onconnectionstatechange = null;
      pc.close();
      if (video) video.srcObject = null;
    };
  }, [isAdmin, online, buildingId, cctv.floor_id, cctv.id, quality, attempt]);

  if (!isAdmin) {
    return (
      <div className="aspect-video w-full rounded-lg flex items-center justify-center text-center px-4"
           style={{ border: "1.5px dashed var(--border)", background: "var(--bg-elevated)" }}>
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Live view: admins only</span>
      </div>
    );
  }

  return (
    <div>
      <div className="relative aspect-video w-full rounded-lg overflow-hidden"
           style={{ border: "1px solid var(--border)", background: "#000" }}>
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-contain" />
        {phase !== "live" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-4"
               style={{ background: "var(--bg-elevated)" }}>
            {phase === "connecting" && (
              <span className="h-3 w-3 rounded-full border-2 border-s-muted border-t-transparent animate-spin" />
            )}
            <span className={`text-xs ${phase === "error" ? "text-s-danger" : "text-s-muted"}`}>{message}</span>
            {phase === "error" && (
              <button
                onClick={() => setAttempt((n) => n + 1)}
                className="px-2.5 py-1 rounded-lg bg-s-elevated border border-s-border text-[10px] font-mono text-s-muted hover:text-s-text transition-colors"
              >
                Try again
              </button>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <span className="font-mono text-[10px] tracking-widest uppercase text-s-muted">
          {phase === "live" ? `Live${quality === "main" ? " · HD" : ""}` : phase === "connecting" ? "Connecting" : "Not live"}
        </span>
        <button
          onClick={() => setQuality((q) => (q === "sub" ? "main" : "sub"))}
          aria-pressed={quality === "main"}
          title={quality === "main" ? "Switch to the standard stream (848×480)" : "Switch to the HD stream (2688×1520)"}
          className={`ml-auto px-2.5 py-1 rounded-lg border text-[10px] font-mono transition-colors ${
            quality === "main" ? "border-s-accent text-s-accent bg-s-elevated" : "border-s-border text-s-muted bg-s-elevated hover:text-s-text"
          }`}
        >
          HD
        </button>
      </div>
    </div>
  );
}

"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { signIn, onAuthChanged } from "@/services/authService";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const unsub = onAuthChanged((u) => { if (u) router.push("/dashboard"); });
    return unsub;
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await signIn(email, password);
      router.push("/dashboard");
    } catch {
      setError("Invalid credentials. Contact your administrator.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left panel — 60% branding */}
      <div className="hidden lg:flex flex-col w-[60%] bg-s-surface relative overflow-hidden">
        <div className="absolute inset-0 bg-dot-grid opacity-40" />
        {/* Radial glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-s-accent opacity-5 rounded-full blur-3xl" />
        <div className="relative z-10 flex flex-col h-full items-center justify-center px-16 gap-6">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-xl bg-s-accent flex items-center justify-center shadow-lg shadow-amber-500/20">
              <span className="font-mono font-bold text-3xl text-s-base">S</span>
            </div>
            <span className="font-bold text-5xl tracking-tight text-s-text">SKYE</span>
          </div>
          <p className="font-mono text-sm text-s-muted tracking-widest text-center uppercase">
            Autonomous Industrial Safety Intelligence
          </p>
          <div className="mt-8 border border-s-border rounded-xl p-6 bg-s-base/40 backdrop-blur-sm space-y-3 max-w-sm w-full">
            {[
              { icon: "◉", label: "Real-time BLE positioning" },
              { icon: "⬡", label: "Kalman-filtered tracking" },
              { icon: "▲", label: "AI-powered audit reports" },
              { icon: "◈", label: "Ghost patrol verification" },
            ].map((f) => (
              <div key={f.label} className="flex items-center gap-3">
                <span className="text-s-accent font-mono text-sm">{f.icon}</span>
                <span className="text-xs text-s-muted">{f.label}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="relative z-10 text-center pb-6 font-mono text-[10px] text-s-muted tracking-widest">
          RESTRICTED ACCESS — AUTHORISED PERSONNEL ONLY
        </p>
      </div>

      {/* Right panel — 40% login form */}
      <div className="flex-1 flex flex-col items-center justify-center bg-s-base px-8">
        <div className="w-full max-w-sm space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-s-text">Security Manager Login</h1>
            <p className="text-sm text-s-muted mt-1">Access the SKYE command dashboard</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Email</label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-s-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <polyline points="22,6 12,13 2,6"/>
                </svg>
                <input
                  type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="manager@facility.com"
                  className="w-full bg-s-surface border border-s-border rounded-lg pl-9 pr-3 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Password</label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-s-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
                <input
                  type={showPw ? "text" : "password"} required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-s-surface border border-s-border rounded-lg pl-9 pr-10 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
                <button type="button" onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-s-muted hover:text-s-text">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    {showPw
                      ? <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>
                      : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
                    }
                  </svg>
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-s-danger/10 border border-s-danger/30 rounded-lg px-3 py-2">
                <span className="text-s-danger text-xs">{error}</span>
              </div>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full py-3 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-2"
            >
              {loading && <span className="h-4 w-4 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
              {loading ? "Authenticating…" : "Sign In"}
            </button>
          </form>

          <p className="font-mono text-[10px] text-s-muted text-center tracking-wider">
            SKYE Sentinel-AI · Authorised Access Only
          </p>
        </div>
      </div>
    </div>
  );
}

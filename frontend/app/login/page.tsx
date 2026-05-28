"use client";
import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn, onAuthChanged, signInWithGoogle } from "@/services/authService";
import { getUserRecord } from "@/services/userService";

function getRedirectPath(role: string, status: string): string {
  if (status === "pending") return "/pending-approval";
  if (status === "suspended") return "/suspended";
  return "/dashboard";
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const registered = searchParams.get("registered");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  function validateEmail(v: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  }

  useEffect(() => {
    const unsub = onAuthChanged(async (u) => {
      if (!u) return;
      const record = await getUserRecord(u.uid);
      if (!record) return;
      router.push(getRedirectPath(record.role, record.status));
    });
    return unsub;
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await signIn(email, password);
      const record = await getUserRecord(user.uid);
      router.push(getRedirectPath(record?.role ?? "user", record?.status ?? "approved"));
      // keep spinner alive — navigation is non-blocking and may take time on cold start
    } catch {
      setError("Invalid credentials. Contact your administrator.");
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      const { role, status } = await signInWithGoogle();
      router.push(getRedirectPath(role, status));
      // keep spinner alive through navigation
    } catch {
      setError("Google sign-in failed. Please try again.");
      setGoogleLoading(false);
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
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-base">
                <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
              </svg>
            </div>
            <span className="font-bold text-5xl tracking-tight text-s-text">SKYE</span>
          </div>
          <p className="font-mono text-sm text-s-muted tracking-widest text-center uppercase">
            Industrial Safety. Intelligently Monitored.
          </p>
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

          {registered === "admin" && (
            <div className="flex items-center gap-2 bg-s-success/10 border border-s-success/30 rounded-lg px-3 py-2.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-success flex-shrink-0">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span className="text-s-success text-xs">Account created. Please sign in to continue.</span>
            </div>
          )}

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
                  type="email" required value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailError && validateEmail(e.target.value)) setEmailError(null);
                  }}
                  onBlur={() => {
                    if (email && !validateEmail(email)) setEmailError("Enter a valid email address");
                  }}
                  placeholder="manager@facility.com"
                  className={`w-full bg-s-surface border rounded-lg pl-9 pr-3 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none transition-colors ${emailError ? "border-s-danger focus:border-s-danger" : "border-s-border focus:border-s-accent"}`}
                />
              </div>
              {emailError && <p className="text-xs text-s-danger font-mono">{emailError}</p>}
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
              type="submit" disabled={loading || googleLoading}
              className="w-full py-3 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-2"
            >
              {loading && <span className="h-4 w-4 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
              {loading ? "Authenticating…" : "Sign In"}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-s-border" />
            <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase">or</span>
            <div className="flex-1 h-px bg-s-border" />
          </div>

          {/* Google button */}
          <button
            onClick={handleGoogle} disabled={googleLoading || loading}
            className="w-full py-2.5 rounded-lg bg-s-elevated border border-s-border text-s-text text-sm font-medium hover:bg-s-surface disabled:opacity-40 transition-colors flex items-center justify-center gap-3"
          >
            {googleLoading ? (
              <span className="h-4 w-4 rounded-full border-2 border-s-muted border-t-transparent animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
            )}
            {googleLoading ? "Connecting…" : "Continue with Google"}
          </button>

          <p className="text-xs text-s-muted text-center">
            No account?{" "}
            <a href="/register" className="text-s-accent hover:underline font-medium">Register here</a>
          </p>

          <p className="font-mono text-[10px] text-s-muted text-center tracking-wider">
            SKYE Sentinel-AI · Authorised Access Only
          </p>
        </div>
      </div>
    </div>
  );
}

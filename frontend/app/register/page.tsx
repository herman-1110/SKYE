"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { signInWithGoogle } from "@/services/authService";
import { registerUser } from "@/services/userService";
import { checkPasswordStrength } from "@/utils/passwordUtils";

const STRENGTH_UI = {
  weak:       { label: "Weak",        segments: 1, bar: "bg-s-danger",    text: "text-s-danger"    },
  fair:       { label: "Fair",        segments: 2, bar: "bg-s-accent",    text: "text-s-accent"    },
  strong:     { label: "Strong",      segments: 3, bar: "bg-s-success",   text: "text-s-success"   },
  very_strong:{ label: "Very Strong", segments: 4, bar: "bg-emerald-400", text: "text-emerald-400" },
} as const;


export default function RegisterPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const strength = checkPasswordStrength(password);
  const ui = STRENGTH_UI[strength.level];
  const canSubmit = (strength.level === "strong" || strength.level === "very_strong")
    && confirmPassword === password
    && !loading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { role } = await registerUser(email, password, displayName);
      if (role === "admin") {
        router.push("/login?registered=admin");
      } else {
        router.push("/pending-approval");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed. Email may already be in use.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      const { role, status } = await signInWithGoogle();
      router.push(getRedirectPath(role, status));
    } catch {
      setError("Google sign-in failed. Please try again.");
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex flex-col w-[60%] bg-s-surface relative overflow-hidden">
        <div className="absolute inset-0 bg-dot-grid opacity-40" />
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
            Autonomous Industrial Safety Intelligence
          </p>
          <div className="mt-4 border border-s-border rounded-xl p-5 bg-s-base/40 backdrop-blur-sm max-w-sm w-full">
            <p className="text-xs text-s-muted leading-relaxed">
              New accounts require approval from a Security Manager before access is granted.
              The first account registered is automatically promoted to admin.
            </p>
          </div>
        </div>
        <p className="relative z-10 text-center pb-6 font-mono text-[10px] text-s-muted tracking-widest">
          RESTRICTED ACCESS — AUTHORISED PERSONNEL ONLY
        </p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col items-center justify-center bg-s-base px-8">
        <div className="w-full max-w-sm space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-s-text">Create Account</h1>
            <p className="text-sm text-s-muted mt-1">
              Already have an account?{" "}
              <a href="/login" className="text-s-accent hover:underline">Sign in</a>
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Display name */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Full Name</label>
              <input
                type="text" required value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Pikachu Sparks"
                className="w-full bg-s-surface border border-s-border rounded-lg px-3 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
              />
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Email</label>
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="pikapika@gmail.com"
                className="w-full bg-s-surface border border-s-border rounded-lg px-3 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Password</label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"} required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••" minLength={6}
                  className="w-full bg-s-surface border border-s-border rounded-lg px-3 pr-10 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
                <button type="button" onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-s-muted hover:text-s-text">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    {showPw
                      ? <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><line x1="1" y1="1" x2="23" y2="23" /></>
                      : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>
                    }
                  </svg>
                </button>
              </div>

              {/* Strength bar — visible once user starts typing */}
              {password.length > 0 && (
                <div className="pt-1 space-y-1.5">
                  <div className="flex gap-1">
                    {([1, 2, 3, 4] as const).map((seg) => (
                      <div
                        key={seg}
                        className={`h-1 flex-1 rounded-full transition-colors duration-200 ${
                          seg <= ui.segments ? ui.bar : "bg-s-border"
                        }`}
                      />
                    ))}
                  </div>
                  <p className={`font-mono text-[10px] tracking-widest uppercase ${ui.text}`}>
                    {ui.label}
                  </p>
                </div>
              )}
            </div>

            {/* Confirm password */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-s-muted tracking-widest uppercase">Confirm Password</label>
              <div className="relative">
                <input
                  type="password" required value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-s-surface border border-s-border rounded-lg px-3 pr-10 py-2.5 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                />
                {confirmPassword.length > 0 && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2">
                    {confirmPassword === password ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-success">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-danger">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    )}
                  </span>
                )}
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-s-danger/10 border border-s-danger/30 rounded-lg px-3 py-2">
                <span className="text-s-danger text-xs">{error}</span>
              </div>
            )}

            <button
              type="submit" disabled={!canSubmit}
              className="w-full py-3 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-2"
            >
              {loading && <span className="h-4 w-4 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
              {loading ? "Creating account…" : "Create Account"}
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
            onClick={handleGoogle} disabled={googleLoading}
            className="w-full py-2.5 rounded-lg bg-s-elevated border border-s-border text-s-text text-sm font-medium hover:bg-s-surface disabled:opacity-40 transition-colors flex items-center justify-center gap-3"
          >
            {googleLoading ? (
              <span className="h-4 w-4 rounded-full border-2 border-s-muted border-t-transparent animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
              </svg>
            )}
            {googleLoading ? "Connecting…" : "Continue with Google"}
          </button>

          <p className="font-mono text-[10px] text-s-muted text-center tracking-wider">
            SKYE Sentinel-AI · Authorised Access Only
          </p>
        </div>
      </div>
    </div>
  );
}

"use client";
import {
  createElement,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import type { User } from "firebase/auth";
import { auth } from "@/config/firebase";
import { onAuthChanged } from "@/services/authService";
import { getUserRecord } from "@/services/userService";
import type { UserRecord } from "@/types/user";
import {
  NO_RECORD_MESSAGE,
  RECORD_TIMEOUT_MS,
  SIGNED_OUT_MESSAGE,
  SUPERSEDED_MESSAGE,
  UNVERIFIED_MESSAGE,
  describeRecordError,
  withTimeout,
} from "@/utils/authCheck";

const UNPROTECTED = ["/login", "/register", "/pending-approval", "/suspended"];

type AuthState = {
  user: User | null;
  userRecord: UserRecord | null;
  isLoading: boolean;
  // Why reading users/{uid} failed, in plain words; null when it didn't.
  // While it's set, the dashboard shows an error screen instead of opening.
  recordError: string | null;
  // Checks the signed-in account again, even when Firebase fires no auth
  // event (signing in again as the account that's already signed in fires
  // none). Resolves to null when a record was found, else to the reason the
  // account can't be used yet.
  recheck: () => Promise<string | null>;
};

const AuthContext = createContext<AuthState>({
  user: null,
  userRecord: null,
  isLoading: true,
  recordError: null,
  recheck: async () => null,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [userRecord, setUserRecord] = useState<UserRecord | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Each check is numbered and only the newest may publish its result, so a
  // slow read can't overwrite a newer one.
  const latestCheck = useRef(0);
  // The uid whose users/{uid} record is currently published, if any.
  const publishedFor = useRef<string | null>(null);

  // Publishes u and its users/{uid} record. Never rejects: a failed read
  // becomes recordError, so isLoading always ends and AUTHENTICATING can't
  // stay up forever.
  const check = useCallback(async (u: User | null): Promise<string | null> => {
    const run = ++latestCheck.current;
    setUser(u);
    setRecordError(null);
    let problem: string | null = null;
    if (u && u.emailVerified) {
      try {
        const record = await withTimeout(getUserRecord(u.uid), RECORD_TIMEOUT_MS);
        if (run !== latestCheck.current) return SUPERSEDED_MESSAGE;
        publishedFor.current = record ? u.uid : null;
        setUserRecord(record);
        if (!record) problem = NO_RECORD_MESSAGE;
      } catch (err) {
        if (run !== latestCheck.current) return SUPERSEDED_MESSAGE;
        console.warn("[useAuth] couldn't read the user record:", err);
        problem = describeRecordError(err);
        publishedFor.current = null;
        setUserRecord(null);
        setRecordError(problem);
      }
    } else {
      publishedFor.current = null;
      setUserRecord(null);
      if (u) problem = UNVERIFIED_MESSAGE;
    }
    setIsLoading(false);
    return problem;
  }, []);

  // Single global auth listener — runs once, state shared app-wide.
  useEffect(() => {
    // Tells the load watchdog in app/layout.tsx that React is running.
    (window as Window & { __skyeAppStarted?: boolean }).__skyeAppStarted = true;
    return onAuthChanged((u) => {
      void check(u);
    });
  }, [check]);

  const recheck = useCallback(async (): Promise<string | null> => {
    const u = auth.currentUser;
    if (!u) return SIGNED_OUT_MESSAGE;
    // This account's record is already published (a returning Google user's
    // auth event usually reads it before /api/auth/google answers). Reading
    // it again could only fail and swap a working dashboard for the error
    // screen.
    if (publishedFor.current === u.uid) return null;
    return check(u);
  }, [check]);

  // Unverified-email redirect — re-evaluates on path/state change.
  useEffect(() => {
    if (isLoading || !user) return;
    if (!user.emailVerified && !UNPROTECTED.some((p) => pathname?.startsWith(p))) {
      router.replace("/pending-approval");
    }
  }, [user, isLoading, pathname, router]);

  return createElement(
    AuthContext.Provider,
    { value: { user, userRecord, isLoading, recordError, recheck } },
    children,
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

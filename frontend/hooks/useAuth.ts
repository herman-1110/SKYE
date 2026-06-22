"use client";
import { createElement, createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import type { User } from "firebase/auth";
import { onAuthChanged } from "@/services/authService";
import { getUserRecord } from "@/services/userService";
import type { UserRecord } from "@/types/user";

const UNPROTECTED = ["/login", "/register", "/pending-approval", "/suspended"];

type AuthState = { user: User | null; userRecord: UserRecord | null; isLoading: boolean };

const AuthContext = createContext<AuthState>({ user: null, userRecord: null, isLoading: true });

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [userRecord, setUserRecord] = useState<UserRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Single global auth listener — runs once, state shared app-wide.
  useEffect(() => {
    const unsubscribe = onAuthChanged(async (u) => {
      setUser(u);
      if (u && u.emailVerified) {
        const record = await getUserRecord(u.uid);
        setUserRecord(record);
      } else {
        setUserRecord(null);
      }
      setIsLoading(false);
    });
    return unsubscribe;
  }, []);

  // Unverified-email redirect — re-evaluates on path/state change.
  useEffect(() => {
    if (isLoading || !user) return;
    if (!user.emailVerified && !UNPROTECTED.some((p) => pathname?.startsWith(p))) {
      router.replace("/pending-approval");
    }
  }, [user, isLoading, pathname, router]);

  return createElement(AuthContext.Provider, { value: { user, userRecord, isLoading } }, children);
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

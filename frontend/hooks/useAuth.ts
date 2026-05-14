"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import type { User } from "firebase/auth";
import { onAuthChanged } from "@/services/authService";
import { getUserRecord } from "@/services/userService";
import type { UserRecord } from "@/types/user";

const UNPROTECTED = ["/login", "/register", "/pending-approval", "/suspended"];

export function useAuth(): { user: User | null; userRecord: UserRecord | null; isLoading: boolean } {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [userRecord, setUserRecord] = useState<UserRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthChanged(async (u) => {
      setUser(u);
      if (u) {
        if (!u.emailVerified) {
          setUserRecord(null);
          setIsLoading(false);
          if (!UNPROTECTED.some((p) => pathname?.startsWith(p))) {
            router.push("/pending-approval");
          }
          return;
        }
        const record = await getUserRecord(u.uid);
        setUserRecord(record);
      } else {
        setUserRecord(null);
      }
      setIsLoading(false);
    });
    return unsubscribe;
  }, [router, pathname]);

  return { user, userRecord, isLoading };
}

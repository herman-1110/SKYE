"use client";
import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { onAuthChanged } from "@/services/authService";
import { getUserRecord } from "@/services/userService";
import type { UserRecord } from "@/types/user";

export function useAuth(): { user: User | null; userRecord: UserRecord | null; isLoading: boolean } {
  const [user, setUser] = useState<User | null>(null);
  const [userRecord, setUserRecord] = useState<UserRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthChanged(async (u) => {
      setUser(u);
      if (u) {
        const record = await getUserRecord(u.uid);
        setUserRecord(record);
      } else {
        setUserRecord(null);
      }
      setIsLoading(false);
    });
    return unsubscribe;
  }, []);

  return { user, userRecord, isLoading };
}

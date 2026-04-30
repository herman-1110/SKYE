"use client";
import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { onAuthChanged } from "@/services/authService";

export function useAuth(): { user: User | null; isLoading: boolean } {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthChanged((u) => {
      setUser(u);
      setIsLoading(false);
    });
    return unsubscribe;
  }, []);

  return { user, isLoading };
}

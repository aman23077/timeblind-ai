"use client";

import { useEffect, useState } from "react";
import { getCurrentUser } from "./api";
import type { UserDetail } from "./api";

export function useAuth() {
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    window.localStorage.removeItem("timeblind-user");
    const expired = () => setUser(null);
    window.addEventListener("timeblind-auth-expired", expired);
    void getCurrentUser().then((profile) => {
      if (!disposed) setUser(profile);
    }).catch(() => {
      if (!disposed) setUser(null);
    }).finally(() => {
      if (!disposed) setLoading(false);
    });
    return () => {
      disposed = true;
      window.removeEventListener("timeblind-auth-expired", expired);
    };
  }, []);
  return { user, setUser, loading };
}

"use client";

import { useEffect, useState } from "react";
import { useUserStore } from "@/store/userStore";
import { UserAPI } from "@/lib/api";

const api = new UserAPI();

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const { user, setUser, clearUser } = useUserStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      api.getProfile()
        .then((profile) => {
          setUser(profile);
        })
        .catch(() => {
          clearUser(); 
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [user, setUser, clearUser]);

  if (loading) {
    return <div className="flex items-center justify-center h-screen">Загрузка...</div>;
  }

  return <>{children}</>;
}

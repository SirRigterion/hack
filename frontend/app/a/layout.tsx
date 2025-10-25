'use client';

import { useUserStore } from "@/store/userStore";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import { UserAPI } from "@/lib/api";
import { Button } from "@/components/ui/button";
// import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const api = new UserAPI();

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const user = useUserStore((s) => s.user);
  const setUser = useUserStore((s) => s.setUser);

  useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  if (!user) return null;

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    router.replace("/login");
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Навбар */}
      <header className="flex items-center justify-between px-6 py-3 bg-white border-b shadow-sm">
        <div className="flex items-center gap-6">
          <h1
            onClick={() => router.push("/a/profile")}
            className="font-semibold text-lg cursor-pointer"
          >
            🎥 VideoConnect
          </h1>

          <nav className="flex gap-3">
            <Button
              variant={pathname === "/a/profile" ? "default" : "ghost"}
              onClick={() => router.push("/a/profile")}
            >
              Профиль
            </Button>
            <Button
              variant={pathname === "/a/call" ? "default" : "ghost"}
              onClick={() => router.push("/a/call")}
            >
              Звонок
            </Button>
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-medium leading-tight">{user.user_full_name}</p>
            <p className="text-xs text-gray-500">{user.user_email}</p>
          </div>
          {/* <Avatar className="w-9 h-9 border">
            <AvatarImage src={user.user_avatar_url || ""} />
            <AvatarFallback>
              {user.user_full_name?.[0]?.toUpperCase() || "U"}
            </AvatarFallback>
          </Avatar> */}
          <Button variant="destructive" onClick={handleLogout} size="sm">
            Выйти
          </Button>
        </div>
      </header>

      {/* Контент */}
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}

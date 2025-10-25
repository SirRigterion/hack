'use client';

import { useEffect, useState } from "react";
import { useUserStore } from "@/store/userStore";
import { useRouter } from "next/navigation";
import { VideoArea } from "@/components/video/VideoArea";
import { ChatPanel } from "@/components/video/ChatPanel";

export default function CallPage() {
  const user = useUserStore((state) => state.user);
  const router = useRouter();

  useEffect(() => {
    if (!user) {
      router.replace("/login");
    }
  }, [user, router]);

  if (!user) return null;

  return (
    <div className="flex h-screen">
      <div className="flex-1 bg-gray-900">
        <VideoArea />
      </div>
      <div className="w-96 border-l border-gray-300">
        <ChatPanel />
      </div>
    </div>
  );
}

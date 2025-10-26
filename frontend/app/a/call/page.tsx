'use client';

import { useEffect } from "react";
import { useUserStore } from "@/store/userStore";
import { useRouter } from "next/navigation";
import VideoArea  from "@/components/video/VideoArea";
import { ChatPanel } from "@/components/video/ChatPanel";
import { Card } from "@/components/ui/card";

export default function CallPage() {
  const user = useUserStore((state) => state.user);
  const router = useRouter();

  useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  if (!user) return null;

  return (
    <div className="flex h-[calc(100vh-64px)] gap-4">
      <Card className="flex-1 bg-black overflow-hidden shadow-lg rounded-xl">
        <VideoArea />
      </Card>
      <Card className="w-96 shadow-lg border border-gray-200 rounded-xl overflow-hidden">
        <ChatPanel />
      </Card>
    </div>
  );
}

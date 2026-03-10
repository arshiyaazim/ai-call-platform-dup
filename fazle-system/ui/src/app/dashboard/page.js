"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Sidebar from "../../components/Sidebar";
import ChatPanel from "../../components/ChatPanel";
import MemoryPanel from "../../components/MemoryPanel";
import TasksPanel from "../../components/TasksPanel";
import KnowledgePanel from "../../components/KnowledgePanel";
import VoicePanel from "../../components/VoicePanel";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("chat");
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!session) return null;

  const panels = {
    chat: <ChatPanel />,
    voice: <VoicePanel />,
    memory: <MemoryPanel />,
    tasks: <TasksPanel />,
    knowledge: <KnowledgePanel />,
  };

  return (
    <div className="flex h-screen">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} user={session.user} />
      <main className="flex-1 overflow-hidden">{panels[activeTab]}</main>
    </div>
  );
}

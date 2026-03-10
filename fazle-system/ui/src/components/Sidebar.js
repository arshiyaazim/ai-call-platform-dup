"use client";

import { signOut } from "next-auth/react";
import { useRouter } from "next/navigation";

const tabs = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "voice", label: "Voice", icon: "🎙️" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "tasks", label: "Tasks", icon: "📋" },
  { id: "knowledge", label: "Knowledge", icon: "📚" },
];

export default function Sidebar({ activeTab, setActiveTab, user }) {
  const router = useRouter();

  return (
    <aside className="w-64 bg-[#12121a] border-r border-gray-800 flex flex-col">
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-fazle-400">Fazle</h1>
        <p className="text-xs text-gray-500 mt-1">Family AI System</p>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-fazle-700/20 text-fazle-300 border border-fazle-700/30"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50"
            }`}
          >
            <span className="text-lg">{tab.icon}</span>
            {tab.label}
          </button>
        ))}

        {user?.role === "admin" && (
          <button
            onClick={() => router.push("/admin/family")}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 transition-colors mt-4 border-t border-gray-800 pt-4"
          >
            <span className="text-lg">👨‍👩‍👧</span>
            Family
          </button>
        )}
      </nav>

      <div className="p-4 border-t border-gray-800">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-fazle-600 flex items-center justify-center text-white text-sm font-bold">
            {user?.name?.[0]?.toUpperCase() || "?"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-200 truncate">
              {user?.name || "User"}
            </p>
            <p className="text-xs text-gray-500 capitalize">
              {user?.relationship || "member"}
            </p>
          </div>
        </div>
        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          className="w-full text-xs text-gray-500 hover:text-gray-300 transition-colors py-1"
        >
          Sign Out
        </button>
      </div>
    </aside>
  );
}

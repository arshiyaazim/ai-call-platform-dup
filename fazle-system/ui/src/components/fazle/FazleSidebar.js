"use client";

import Link from "next/link";
import { signOut } from "next-auth/react";
import { useRouter } from "next/navigation";

const navItems = [
  { href: "/dashboard/fazle", label: "Overview", icon: "📊" },
  { href: "/dashboard/fazle/memory", label: "Memory", icon: "🧠" },
  { href: "/dashboard/fazle/agents", label: "Agents", icon: "🤖" },
  { href: "/dashboard/fazle/tools", label: "Tools", icon: "🔧" },
  { href: "/dashboard/fazle/tasks", label: "Tasks", icon: "📋" },
  { href: "/dashboard/fazle/persona", label: "Persona", icon: "🎭" },
  { href: "/dashboard/fazle/logs", label: "Logs", icon: "📜" },
];

export default function FazleSidebar({ pathname, user }) {
  const router = useRouter();

  const isActive = (href) => {
    if (href === "/dashboard/fazle") return pathname === href;
    return pathname.startsWith(href);
  };

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 bg-[#12121a] border-r border-gray-800 flex-col shrink-0">
        <div className="p-6 border-b border-gray-800">
          <Link href="/dashboard/fazle" className="block">
            <h1 className="text-xl font-bold text-fazle-400">Fazle AI</h1>
            <p className="text-[10px] text-gray-500 mt-0.5 uppercase tracking-widest">
              Control Dashboard
            </p>
          </Link>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? "bg-fazle-700/20 text-fazle-300 border border-fazle-700/30"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </Link>
          ))}

          <div className="pt-4 mt-4 border-t border-gray-800">
            <button
              onClick={() => router.push("/dashboard")}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 transition-colors"
            >
              <span className="text-lg">←</span>
              Back to Fazle
            </button>
          </div>
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-fazle-600 flex items-center justify-center text-white text-sm font-bold">
              {user?.name?.[0]?.toUpperCase() || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate">
                {user?.name || "Admin"}
              </p>
              <p className="text-xs text-gray-500">Admin</p>
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

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[#12121a] border-t border-gray-800 z-50 safe-area-bottom">
        <div className="flex justify-around items-center h-16 overflow-x-auto">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center flex-1 h-full min-w-[56px] transition-colors ${
                isActive(item.href) ? "text-fazle-400" : "text-gray-500"
              }`}
            >
              <span className="text-xl">{item.icon}</span>
              <span className="text-[9px] mt-0.5">{item.label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </>
  );
}

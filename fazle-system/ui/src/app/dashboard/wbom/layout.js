"use client";

import { useSession } from "next-auth/react";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/dashboard/wbom", label: "Dashboard", icon: "📊" },
  { href: "/dashboard/wbom/employees", label: "Employees", icon: "👥" },
  { href: "/dashboard/wbom/transactions", label: "Transactions", icon: "💰" },
  { href: "/dashboard/wbom/payments", label: "Payments", icon: "📤" },
  { href: "/dashboard/wbom/clients", label: "Clients", icon: "🏢" },
  { href: "/dashboard/wbom/applications", label: "Applications", icon: "📋" },
  { href: "/dashboard/wbom/audit", label: "Audit Log", icon: "📜" },
];

function WbomSidebar({ pathname }) {
  return (
    <aside className="w-56 bg-[#111118] border-r border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <h2 className="text-lg font-bold text-white">WBOM</h2>
        <p className="text-xs text-gray-500">Business Operations</p>
      </div>
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href ||
            (item.href !== "/dashboard/wbom" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-blue-900/30 text-blue-400 border-r-2 border-blue-400"
                  : "text-gray-400 hover:text-white hover:bg-gray-800/50"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <Link href="/dashboard" className="text-xs text-gray-500 hover:text-gray-300">
          ← Back to Dashboard
        </Link>
      </div>
    </aside>
  );
}

export default function WbomLayout({ children }) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

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

  return (
    <div className="flex h-screen bg-[#0a0a0f]">
      <WbomSidebar pathname={pathname} />
      <main className="flex-1 overflow-auto p-6">
        {children}
      </main>
    </div>
  );
}

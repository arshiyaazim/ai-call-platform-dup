"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../lib/wbom-api";

function StatCard({ label, value, icon }) {
  return (
    <div className="bg-[#111118] rounded-lg p-5 border border-gray-800">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">{value ?? "—"}</p>
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

export default function WbomDashboard() {
  const { get } = useWbomApi();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const [empCount, txCount, pendingPayments] = await Promise.all([
          get("/employees/count").catch(() => ({ count: "?" })),
          get("/transactions/count").catch(() => ({ count: "?" })),
          get("/payment/pending?limit=5").catch(() => []),
        ]);
        setStats({
          employees: empCount?.count ?? "?",
          transactions: txCount?.count ?? "?",
          pendingPayments: Array.isArray(pendingPayments) ? pendingPayments.length : 0,
        });
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">WBOM Dashboard</h1>
      {error && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{error}</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Employees" value={stats?.employees} icon="👥" />
        <StatCard label="Transactions" value={stats?.transactions} icon="💰" />
        <StatCard label="Pending Payments" value={stats?.pendingPayments} icon="⏳" />
      </div>
    </div>
  );
}

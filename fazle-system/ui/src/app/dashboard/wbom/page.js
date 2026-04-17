"use client";

import { useWbomCount, useWbomList } from "../../../lib/wbom-api";

function StatCard({ label, value, icon, loading }) {
  return (
    <div className="bg-[#111118] rounded-lg p-5 border border-gray-800">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">
            {loading ? <span className="animate-pulse bg-gray-700 rounded w-12 h-7 inline-block" /> : (value ?? "—")}
          </p>
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

export default function WbomDashboard() {
  const emp = useWbomCount("/employees/count");
  const tx  = useWbomCount("/transactions/count");
  const pay = useWbomList("/payment/pending?limit=5", [], "payments");

  const anyError = pay.error;

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">WBOM Dashboard</h1>
      {anyError && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{anyError}</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Employees" value={emp.total} icon="👥" loading={emp.loading} />
        <StatCard label="Transactions" value={tx.total} icon="💰" loading={tx.loading} />
        <StatCard label="Pending Payments" value={pay.meta.total} icon="⏳" loading={pay.loading} />
      </div>
    </div>
  );
}

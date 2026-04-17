"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function ClientsPage() {
  const { get } = useWbomApi();
  const [clients, setClients] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await get("/clients?limit=100");
        setClients(Array.isArray(data) ? data : []);
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Clients</h1>
      {error && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{error}</div>
      )}
      <div className="bg-[#111118] rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-left">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Balance</th>
              <th className="px-4 py-3">Active</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.client_id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{c.client_id}</td>
                <td className="px-4 py-3 font-medium text-white">{c.name}</td>
                <td className="px-4 py-3">{c.phone || "—"}</td>
                <td className="px-4 py-3">{c.company_name || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    c.client_type === "VIP" ? "bg-purple-900/30 text-purple-400" :
                    c.client_type === "Corporate" ? "bg-blue-900/30 text-blue-400" :
                    "bg-gray-700 text-gray-400"
                  }`}>
                    {c.client_type}
                  </span>
                </td>
                <td className="px-4 py-3">৳{Number(c.outstanding_balance || 0).toLocaleString()}</td>
                <td className="px-4 py-3">{c.is_active ? "✅" : "❌"}</td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No clients</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

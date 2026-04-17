"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function AuditLogPage() {
  const { get } = useWbomApi();
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const params = filter ? `?entity_type=${encodeURIComponent(filter)}&limit=100` : "?limit=100";
        const data = await get(`/audit${params}`);
        setLogs(Array.isArray(data) ? data : []);
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get, filter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Audit Log</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-[#111118] border border-gray-700 rounded px-3 py-2 text-sm text-white"
        >
          <option value="">All types</option>
          <option value="transaction">Transactions</option>
          <option value="staging_payment">Payments</option>
          <option value="client">Clients</option>
          <option value="job_application">Applications</option>
        </select>
      </div>
      {error && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{error}</div>
      )}
      <div className="bg-[#111118] rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-left">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Entity</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.audit_id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 text-xs font-mono">{log.created_at?.slice(0, 19)}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-xs bg-blue-900/30 text-blue-400">
                    {log.event}
                  </span>
                </td>
                <td className="px-4 py-3">{log.actor}</td>
                <td className="px-4 py-3 text-xs">
                  {log.entity_type && `${log.entity_type}`}
                  {log.entity_id && ` #${log.entity_id}`}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 max-w-xs truncate">
                  {log.payload ? JSON.stringify(log.payload).slice(0, 120) : "—"}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No audit logs</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

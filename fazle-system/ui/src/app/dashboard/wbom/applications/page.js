"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function ApplicationsPage() {
  const { get, put } = useWbomApi();
  const [apps, setApps] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await get("/job-applications?limit=100");
        setApps(Array.isArray(data) ? data : []);
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get]);

  async function updateStatus(id, newStatus) {
    try {
      await put(`/job-applications/${id}`, { status: newStatus });
      setApps((prev) =>
        prev.map((a) => (a.application_id === id ? { ...a, status: newStatus } : a))
      );
    } catch (e) {
      setError(e.message);
    }
  }

  const STATUS_COLORS = {
    Applied: "bg-blue-900/30 text-blue-400",
    Screened: "bg-yellow-900/30 text-yellow-400",
    Interviewed: "bg-purple-900/30 text-purple-400",
    Hired: "bg-green-900/30 text-green-400",
    Rejected: "bg-red-900/30 text-red-400",
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Job Applications</h1>
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
              <th className="px-4 py-3">Position</th>
              <th className="px-4 py-3">Experience</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((a) => (
              <tr key={a.application_id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{a.application_id}</td>
                <td className="px-4 py-3 font-medium text-white">{a.applicant_name}</td>
                <td className="px-4 py-3">{a.phone}</td>
                <td className="px-4 py-3">{a.position || "—"}</td>
                <td className="px-4 py-3 text-xs">{a.experience || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[a.status] || "bg-gray-700 text-gray-400"}`}>
                    {a.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs">{a.source}</td>
                <td className="px-4 py-3">
                  <select
                    value={a.status}
                    onChange={(e) => updateStatus(a.application_id, e.target.value)}
                    className="bg-[#0a0a0f] border border-gray-700 rounded px-2 py-1 text-xs text-white"
                  >
                    <option value="Applied">Applied</option>
                    <option value="Screened">Screened</option>
                    <option value="Interviewed">Interviewed</option>
                    <option value="Hired">Hired</option>
                    <option value="Rejected">Rejected</option>
                  </select>
                </td>
              </tr>
            ))}
            {apps.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No applications</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

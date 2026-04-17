"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function PaymentsPage() {
  const { get, post } = useWbomApi();
  const [pending, setPending] = useState([]);
  const [error, setError] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);

  async function loadPending() {
    try {
      const data = await get("/payment/pending?limit=50");
      setPending(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { loadPending(); }, [get]);

  async function approveAndExecute(staging_id) {
    try {
      setActionMsg(null);
      await post("/payment/approve", { staging_id, approved_by: "admin" });
      const result = await post(`/payment/execute/${staging_id}?executed_by=admin`, {});
      setActionMsg(result.message || "Executed");
      loadPending();
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
  }

  async function reject(staging_id) {
    try {
      setActionMsg(null);
      await post(`/payment/reject/${staging_id}?rejected_by=admin&reason=manual`, {});
      setActionMsg("Rejected");
      loadPending();
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Pending Payments</h1>
      {error && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{error}</div>
      )}
      {actionMsg && (
        <div className="bg-blue-900/30 text-blue-400 p-3 rounded mb-4 text-sm">{actionMsg}</div>
      )}
      <div className="bg-[#111118] rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-left">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((p) => (
              <tr key={p.id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{p.id}</td>
                <td className="px-4 py-3 font-medium text-white">{p.employee_name}</td>
                <td className="px-4 py-3">৳{Number(p.amount || 0).toLocaleString()}</td>
                <td className="px-4 py-3">{p.payment_method}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-xs bg-yellow-900/30 text-yellow-400">
                    {p.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs">{p.created_at?.slice(0, 16)}</td>
                <td className="px-4 py-3 flex gap-2">
                  <button
                    onClick={() => approveAndExecute(p.id)}
                    className="px-3 py-1 bg-green-700 hover:bg-green-600 text-white rounded text-xs"
                  >
                    Approve & Execute
                  </button>
                  <button
                    onClick={() => reject(p.id)}
                    className="px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-xs"
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
            {pending.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No pending payments</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

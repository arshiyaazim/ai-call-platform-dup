"use client";

import { useState } from "react";
import { useWbomApi, useWbomList, formatCell } from "../../../../lib/wbom-api";
import WbomTable, { StatusBadge, MetaBar } from "../../../../lib/wbom-table";

export default function PaymentsPage() {
  const { post } = useWbomApi();
  const { rows, meta, loading, error, reload } = useWbomList("/payment/pending?limit=50", [], "payments");
  const [actionMsg, setActionMsg] = useState(null);

  async function approveAndExecute(staging_id) {
    try {
      setActionMsg(null);
      await post("/payment/approve", { staging_id, approved_by: "admin" });
      const result = await post(`/payment/execute/${staging_id}?executed_by=admin`, {});
      setActionMsg(result.message || "Executed");
      reload();
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
  }

  async function reject(staging_id) {
    try {
      setActionMsg(null);
      await post(`/payment/reject/${staging_id}?rejected_by=admin&reason=manual`, {});
      setActionMsg("Rejected");
      reload();
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
  }

  const COLUMNS = [
    { key: "id", label: "ID" },
    { key: "employee_name", label: "Employee" },
    { key: "amount", label: "Amount", render: (v) => formatCell(v, "amount") },
    { key: "method", label: "Method" },
    { key: "status", label: "Status", render: (v) => <StatusBadge status={v} /> },
    { key: "created_at", label: "Created", render: (v) => formatCell(v, "created_at") },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Pending Payments</h1>
      {actionMsg && (
        <div className="bg-blue-900/30 text-blue-400 p-3 rounded mb-4 text-sm">{actionMsg}</div>
      )}
      <MetaBar meta={meta} entityName="payments" />
      <WbomTable
        rows={rows}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No pending payments"
        actions={(row) => (
          <div className="flex gap-2">
            <button
              onClick={() => approveAndExecute(row.id)}
              className="px-3 py-1 bg-green-700 hover:bg-green-600 text-white rounded text-xs"
            >
              Approve & Execute
            </button>
            <button
              onClick={() => reject(row.id)}
              className="px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-xs"
            >
              Reject
            </button>
          </div>
        )}
      />
    </div>
  );
}

"use client";

import { useWbomApi, useWbomList } from "../../../../lib/wbom-api";
import WbomTable, { StatusBadge, MetaBar } from "../../../../lib/wbom-table";

export default function ApplicationsPage() {
  const { put } = useWbomApi();
  const { rows, meta, loading, error, reload } = useWbomList("/job-applications?limit=100", [], "applications");

  async function updateStatus(id, newStatus) {
    try {
      await put(`/job-applications/${id}`, { status: newStatus });
      reload();
    } catch (e) {
      alert(e.message);
    }
  }

  const COLUMNS = [
    { key: "id", label: "ID" },
    { key: "name", label: "Name" },
    { key: "phone", label: "Phone" },
    { key: "position", label: "Position" },
    { key: "experience", label: "Experience" },
    { key: "status", label: "Status", render: (v) => <StatusBadge status={v} /> },
    { key: "source", label: "Source" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Job Applications</h1>
      <MetaBar meta={meta} entityName="applications" />
      <WbomTable
        rows={rows}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No applications"
        actions={(row) => (
          <select
            value={row.status || ""}
            onChange={(e) => updateStatus(row.id, e.target.value)}
            className="bg-[#0a0a0f] border border-gray-700 rounded px-2 py-1 text-xs text-white"
          >
            <option value="Applied">Applied</option>
            <option value="Screened">Screened</option>
            <option value="Interviewed">Interviewed</option>
            <option value="Hired">Hired</option>
            <option value="Rejected">Rejected</option>
          </select>
        )}
      />
    </div>
  );
}

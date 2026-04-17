"use client";

import { useState } from "react";
import { useWbomList, formatCell } from "../../../../lib/wbom-api";
import WbomTable, { MetaBar } from "../../../../lib/wbom-table";

const COLUMNS = [
  { key: "time", label: "Time", render: (v) => formatCell(v, "time") },
  { key: "event", label: "Event" },
  { key: "actor", label: "Actor" },
  { key: "entity", label: "Entity", render: (v, row) => `${v || ""}${row.entity_id ? ` #${row.entity_id}` : ""}` },
  { key: "payload", label: "Details", render: (v) => {
    if (!v) return "—";
    const s = typeof v === "string" ? v : JSON.stringify(v);
    return <span className="text-gray-500 text-xs max-w-xs truncate block">{s.slice(0, 120)}</span>;
  }},
];

export default function AuditLogPage() {
  const [filter, setFilter] = useState("");
  const params = filter ? `?entity_type=${encodeURIComponent(filter)}&limit=100` : "?limit=100";
  const { rows, meta, loading, error } = useWbomList(`/audit${params}`, [filter], "audit");

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
      <MetaBar meta={meta} entityName="audit logs" />
      <WbomTable
        rows={rows}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No audit logs"
        hiddenKeys={new Set(["entity_id"])}
      />
    </div>
  );
}

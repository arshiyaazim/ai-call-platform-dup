"use client";

import { useWbomList, formatCell } from "../../../../lib/wbom-api";
import WbomTable, { StatusBadge, MetaBar } from "../../../../lib/wbom-table";

const COLUMNS = [
  { key: "id", label: "ID" },
  { key: "name", label: "Name" },
  { key: "phone", label: "Phone" },
  { key: "company", label: "Company" },
  { key: "type", label: "Type", render: (v) => <StatusBadge status={v} /> },
  { key: "balance", label: "Balance", render: (v) => formatCell(v, "balance") },
  { key: "is_active", label: "Active", render: (v) => (v ? "Yes" : "No") },
];

export default function ClientsPage() {
  const { rows, meta, loading, error } = useWbomList("/clients?limit=100", [], "clients");

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Clients</h1>
      <MetaBar meta={meta} entityName="clients" />
      <WbomTable
        rows={rows}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No clients"
      />
    </div>
  );
}

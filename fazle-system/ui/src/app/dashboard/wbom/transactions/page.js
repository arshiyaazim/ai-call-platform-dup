"use client";

import { useWbomList, formatCell } from "../../../../lib/wbom-api";
import WbomTable, { StatusBadge, MetaBar } from "../../../../lib/wbom-table";

const COLUMNS = [
  { key: "id", label: "ID" },
  { key: "employee_name", label: "Employee" },
  { key: "type", label: "Type", render: (v) => <StatusBadge status={v} /> },
  { key: "amount", label: "Amount", render: (v) => formatCell(v, "amount") },
  { key: "method", label: "Method" },
  { key: "status", label: "Status", render: (v) => <StatusBadge status={v} /> },
  { key: "date", label: "Date", render: (v) => formatCell(v, "date") },
];

export default function TransactionsPage() {
  const { rows, meta, loading, error } = useWbomList("/transactions?limit=100", [], "transactions");

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Transactions</h1>
      <MetaBar meta={meta} entityName="transactions" />
      <WbomTable
        rows={rows}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No transactions today"
      />
    </div>
  );
}

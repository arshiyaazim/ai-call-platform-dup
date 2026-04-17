"use client";

import { useState, useMemo } from "react";
import { useWbomList, formatCell } from "../../../../lib/wbom-api";
import WbomTable, { StatusBadge, MetaBar } from "../../../../lib/wbom-table";

const COLUMNS = [
  { key: "id", label: "ID" },
  { key: "name", label: "Name" },
  { key: "phone", label: "Phone" },
  { key: "designation", label: "Designation" },
  { key: "status", label: "Status", render: (v) => <StatusBadge status={v} /> },
  { key: "salary", label: "Basic Salary", render: (v) => formatCell(v, "salary") },
];

export default function EmployeesPage() {
  const { rows, meta, loading, error } = useWbomList("/employees?limit=100", [], "employees");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (e) =>
        (e.name || "").toLowerCase().includes(q) ||
        (e.phone || "").includes(q)
    );
  }, [rows, search]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Employees</h1>
        <input
          type="text"
          placeholder="Search name or phone…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-[#111118] border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 w-64"
        />
      </div>
      <MetaBar meta={meta} entityName="employees" />
      <WbomTable
        rows={filtered}
        columns={COLUMNS}
        loading={loading}
        error={error}
        emptyMsg="No employees found"
      />
    </div>
  );
}

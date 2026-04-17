"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function EmployeesPage() {
  const { get } = useWbomApi();
  const [employees, setEmployees] = useState([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await get("/employees?limit=100");
        setEmployees(Array.isArray(data) ? data : []);
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get]);

  const filtered = search
    ? employees.filter(
        (e) =>
          (e.employee_name || "").toLowerCase().includes(search.toLowerCase()) ||
          (e.employee_mobile || "").includes(search)
      )
    : employees;

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
              <th className="px-4 py-3">Designation</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Basic Salary</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((emp) => (
              <tr key={emp.employee_id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{emp.employee_id}</td>
                <td className="px-4 py-3 font-medium text-white">{emp.employee_name}</td>
                <td className="px-4 py-3">{emp.employee_mobile}</td>
                <td className="px-4 py-3">{emp.designation || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    emp.status === "Active" ? "bg-green-900/30 text-green-400" : "bg-gray-700 text-gray-400"
                  }`}>
                    {emp.status}
                  </span>
                </td>
                <td className="px-4 py-3">৳{Number(emp.basic_salary || 0).toLocaleString()}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No employees found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

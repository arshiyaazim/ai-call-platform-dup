"use client";

import { useEffect, useState } from "react";
import { useWbomApi } from "../../../../lib/wbom-api";

export default function TransactionsPage() {
  const { get } = useWbomApi();
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const today = new Date().toISOString().slice(0, 10);
        const data = await get(`/transactions/daily-summary?date=${today}`);
        setTransactions(Array.isArray(data) ? data : []);
      } catch (e) {
        setError(e.message);
      }
    }
    load();
  }, [get]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">Transactions</h1>
      {error && (
        <div className="bg-red-900/30 text-red-400 p-3 rounded mb-4 text-sm">{error}</div>
      )}
      <div className="bg-[#111118] rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-left">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Date</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.transaction_id} className="border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{tx.transaction_id}</td>
                <td className="px-4 py-3">{tx.employee_name || tx.employee_id}</td>
                <td className="px-4 py-3">{tx.transaction_type}</td>
                <td className="px-4 py-3 font-medium text-white">৳{Number(tx.amount || 0).toLocaleString()}</td>
                <td className="px-4 py-3">{tx.payment_method}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    tx.status === "Completed" ? "bg-green-900/30 text-green-400" :
                    tx.status === "Pending" ? "bg-yellow-900/30 text-yellow-400" :
                    "bg-red-900/30 text-red-400"
                  }`}>
                    {tx.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs">{tx.transaction_date}</td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No transactions today</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

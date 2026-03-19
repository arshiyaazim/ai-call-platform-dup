"use client";

export default function DataTable({ columns, data, loading, emptyMessage = "No data found." }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-pulse text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-gray-500 text-sm">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-800">
            {columns.map((col) => (
              <th
                key={col.key}
                className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3"
                style={col.width ? { width: col.width } : undefined}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {data.map((row, i) => (
            <tr
              key={row.id || i}
              className="hover:bg-gray-800/30 transition-colors group"
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3.5 text-sm text-gray-300">
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

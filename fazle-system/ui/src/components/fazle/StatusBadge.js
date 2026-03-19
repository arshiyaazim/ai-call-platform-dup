"use client";

const variants = {
  active: "bg-green-500/20 text-green-300 border-green-500/30",
  inactive: "bg-gray-700/30 text-gray-400 border-gray-600/30",
  enabled: "bg-green-500/20 text-green-300 border-green-500/30",
  disabled: "bg-red-500/20 text-red-300 border-red-500/30",
  pending: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  running: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  paused: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  completed: "bg-green-500/20 text-green-300 border-green-500/30",
  failed: "bg-red-500/20 text-red-300 border-red-500/30",
  locked: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  unlocked: "bg-gray-700/30 text-gray-400 border-gray-600/30",
  installed: "bg-teal-500/20 text-teal-300 border-teal-500/30",
};

export default function StatusBadge({ status, className = "" }) {
  const key = status?.toLowerCase() || "inactive";
  const classes = variants[key] || variants.inactive;
  return (
    <span
      className={`inline-flex items-center text-xs font-medium px-2.5 py-0.5 rounded-full border ${classes} ${className}`}
    >
      {status}
    </span>
  );
}

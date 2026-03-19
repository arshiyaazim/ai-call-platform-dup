"use client";

import { useState, useRef, useEffect } from "react";

export default function ActionDropdown({ actions }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="text-gray-400 hover:text-gray-200 p-1.5 rounded-lg hover:bg-gray-800/50 transition-colors"
      >
        <svg
          className="w-4 h-4"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-44 bg-[#1a1a2e] border border-gray-700 rounded-lg shadow-xl z-50 py-1">
          {actions.map((action, i) => (
            <button
              key={i}
              onClick={() => {
                setOpen(false);
                action.onClick();
              }}
              disabled={action.disabled}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                action.danger
                  ? "text-red-400 hover:bg-red-500/10"
                  : "text-gray-300 hover:bg-gray-800/50"
              } ${action.disabled ? "opacity-40 cursor-not-allowed" : ""}`}
            >
              {action.icon && <span className="mr-2">{action.icon}</span>}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

export default function PageHeader({ title, description, actions }) {
  return (
    <div className="border-b border-gray-800 p-6 flex items-center justify-between shrink-0">
      <div>
        <h2 className="text-xl font-semibold text-gray-200">{title}</h2>
        {description && (
          <p className="text-xs text-gray-500 mt-1">{description}</p>
        )}
      </div>
      {actions && <div className="flex gap-3">{actions}</div>}
    </div>
  );
}

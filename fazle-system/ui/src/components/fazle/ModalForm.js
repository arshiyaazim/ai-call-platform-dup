"use client";

export default function ModalForm({ open, title, onClose, children, onSubmit }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
      <div className="bg-[#1a1a2e] border border-gray-700 rounded-2xl max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
          <h3 className="text-lg font-semibold text-gray-200">{title}</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl transition-colors"
          >
            ✕
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit?.(e);
          }}
          className="p-6 space-y-4"
        >
          {children}
        </form>
      </div>
    </div>
  );
}

export function FormField({ label, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-300 mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

export function FormInput({ label, ...props }) {
  return (
    <FormField label={label}>
      <input
        className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
        {...props}
      />
    </FormField>
  );
}

export function FormSelect({ label, options, ...props }) {
  return (
    <FormField label={label}>
      <select
        className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-fazle-500 transition-colors"
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </FormField>
  );
}

export function FormTextarea({ label, ...props }) {
  return (
    <FormField label={label}>
      <textarea
        className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
        rows={4}
        {...props}
      />
    </FormField>
  );
}

export function FormActions({ submitLabel = "Save", onCancel }) {
  return (
    <div className="flex justify-end gap-3 pt-2">
      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2.5 text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
      )}
      <button
        type="submit"
        className="px-6 py-2.5 text-sm bg-fazle-600 hover:bg-fazle-700 text-white rounded-lg font-medium transition-colors"
      >
        {submitLabel}
      </button>
    </div>
  );
}

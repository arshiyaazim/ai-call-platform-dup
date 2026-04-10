"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";

const ROLES = ["client", "employee", "family", "friend", "job_seeker", "unknown"];
const LANGUAGES = [
  { value: "bn", label: "বাংলা (Bangla)" },
  { value: "en", label: "English" },
  { value: "mixed", label: "Mixed (Bangla + English)" },
];

export default function ContactsPanel() {
  const { data: session } = useSession();
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ phone: "", name: "", role: "unknown", language_pref: "bn", sub_role: "" });
  const [message, setMessage] = useState(null);

  const authHeaders = useCallback(
    () => ({
      "Content-Type": "application/json",
      ...(session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {}),
    }),
    [session]
  );

  const loadContacts = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter !== "all" ? `?role=${filter}` : "";
      const res = await fetch(`/api/fazle/contacts${params}`, { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setContacts(data.contacts || []);
      }
    } catch {
      setContacts([]);
    } finally {
      setLoading(false);
    }
  }, [filter, authHeaders]);

  useEffect(() => {
    loadContacts();
  }, [loadContacts]);

  const saveContact = async (e) => {
    e.preventDefault();
    setMessage(null);
    try {
      const res = await fetch("/api/fazle/contacts/role", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Contact saved" });
        setEditing(null);
        setForm({ phone: "", name: "", role: "unknown", language_pref: "bn", sub_role: "" });
        loadContacts();
      } else {
        setMessage({ type: "error", text: "Failed to save" });
      }
    } catch {
      setMessage({ type: "error", text: "Service unavailable" });
    }
  };

  const setLanguage = async (phone, language) => {
    try {
      await fetch("/api/fazle/contacts/language", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ phone, language }),
      });
      loadContacts();
    } catch {
      // silent
    }
  };

  const startEdit = (contact) => {
    setEditing(contact.phone);
    setForm({
      phone: contact.phone,
      name: contact.name || "",
      role: contact.role || "unknown",
      language_pref: contact.language_pref || "bn",
      sub_role: contact.sub_role || "",
    });
  };

  const startAdd = () => {
    setEditing("new");
    setForm({ phone: "", name: "", role: "unknown", language_pref: "bn", sub_role: "" });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-200">Contacts</h2>
            <p className="text-xs text-gray-500">Manage contact roles and language preferences</p>
          </div>
          <button
            onClick={startAdd}
            className="px-3 py-1.5 bg-fazle-600 hover:bg-fazle-700 text-white rounded-lg text-sm font-medium"
          >
            + Add Contact
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="p-3 border-b border-gray-800 flex gap-2 flex-wrap">
        {["all", ...ROLES].map((r) => (
          <button
            key={r}
            onClick={() => setFilter(r)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              filter === r ? "bg-fazle-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {r === "all" ? "All" : r.replace("_", " ")}
          </button>
        ))}
      </div>

      {message && (
        <div
          className={`mx-4 mt-2 px-3 py-2 rounded text-sm ${
            message.type === "success" ? "bg-green-900/50 text-green-300" : "bg-red-900/50 text-red-300"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Edit / Add form */}
      {editing && (
        <div className="p-4 border-b border-gray-800 bg-[#12121a]">
          <form onSubmit={saveContact} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="Phone (e.g. 8801234567890)"
                className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
                required
                disabled={editing !== "new"}
              />
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Name"
                className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-fazle-500"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r.replace("_", " ")}
                  </option>
                ))}
              </select>
              <select
                value={form.language_pref}
                onChange={(e) => setForm({ ...form, language_pref: e.target.value })}
                className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-fazle-500"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={form.sub_role}
                onChange={(e) => setForm({ ...form, sub_role: e.target.value })}
                placeholder="Sub-role (optional)"
                className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                className="px-4 py-2 bg-fazle-600 hover:bg-fazle-700 text-white rounded-lg text-sm font-medium"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Contact list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading contacts...</div>
        ) : contacts.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No contacts found</div>
        ) : (
          <div className="divide-y divide-gray-800">
            {contacts.map((c) => (
              <div
                key={c.phone}
                className="p-4 hover:bg-[#12121a] flex items-center justify-between"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-200 font-medium">{c.name || c.phone}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        c.role === "client"
                          ? "bg-blue-900/50 text-blue-300"
                          : c.role === "employee"
                          ? "bg-green-900/50 text-green-300"
                          : c.role === "family"
                          ? "bg-purple-900/50 text-purple-300"
                          : c.role === "friend"
                          ? "bg-yellow-900/50 text-yellow-300"
                          : "bg-gray-700 text-gray-400"
                      }`}
                    >
                      {c.role}
                    </span>
                    {c.sub_role && (
                      <span className="text-xs text-gray-500">({c.sub_role})</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{c.phone}</div>
                </div>
                <div className="flex items-center gap-3">
                  <select
                    value={c.language_pref || "bn"}
                    onChange={(e) => setLanguage(c.phone, e.target.value)}
                    className="bg-[#1a1a2e] border border-gray-700 rounded px-2 py-1 text-xs text-gray-300"
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l.value} value={l.value}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => startEdit(c)}
                    className="px-2 py-1 text-xs text-gray-400 hover:text-fazle-400"
                  >
                    Edit
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

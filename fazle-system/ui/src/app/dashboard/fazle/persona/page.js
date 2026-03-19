"use client";

import { useState, useEffect } from "react";
import { useApi } from "../../../../lib/api";
import PageHeader from "../../../../components/fazle/PageHeader";

export default function PersonaEditorPage() {
  const api = useApi();
  const [persona, setPersona] = useState({
    name: "",
    tone: "",
    language: "",
    speaking_style: "",
    knowledge_notes: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchPersona = async () => {
      setLoading(true);
      try {
        const data = await api.get("/admin/persona");
        setPersona({
          name: data.name || "",
          tone: data.tone || "",
          language: data.language || "",
          speaking_style: data.speaking_style || data.style || "",
          knowledge_notes: data.knowledge_notes || data.notes || "",
        });
      } catch {
        // Use defaults
        setPersona({
          name: "Azim",
          tone: "Warm, caring, knowledgeable",
          language: "English",
          speaking_style: "Natural conversational tone with occasional humor. Speaks like a thoughtful friend.",
          knowledge_notes: "Family AI assistant with deep personal knowledge.",
        });
      } finally {
        setLoading(false);
      }
    };
    fetchPersona();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await api.put("/admin/persona", persona);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <PageHeader title="Voice Persona Editor" description="Configure the AI voice personality" />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-pulse text-gray-500 text-sm">Loading persona...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <PageHeader
        title="Voice Persona Editor"
        description="Configure the AI voice personality and speaking style"
        actions={
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-fazle-600 hover:bg-fazle-700 disabled:opacity-50 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {saving ? "Saving..." : saved ? "Saved!" : "Save Changes"}
          </button>
        }
      />

      <div className="p-6 max-w-2xl space-y-6 pb-20 md:pb-6">
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {saved && (
          <div className="text-green-400 text-sm bg-green-400/10 border border-green-400/20 rounded-lg px-4 py-3">
            Persona saved successfully!
          </div>
        )}

        <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Name
            </label>
            <input
              type="text"
              value={persona.name}
              onChange={(e) => setPersona({ ...persona, name: e.target.value })}
              placeholder="AI persona name"
              className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Tone
            </label>
            <input
              type="text"
              value={persona.tone}
              onChange={(e) => setPersona({ ...persona, tone: e.target.value })}
              placeholder="e.g. Warm, professional, friendly"
              className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Language
            </label>
            <input
              type="text"
              value={persona.language}
              onChange={(e) =>
                setPersona({ ...persona, language: e.target.value })
              }
              placeholder="e.g. English, Bangla, Arabic"
              className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Speaking Style
            </label>
            <textarea
              value={persona.speaking_style}
              onChange={(e) =>
                setPersona({ ...persona, speaking_style: e.target.value })
              }
              placeholder="Describe how the AI should speak..."
              rows={4}
              className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Knowledge Notes
            </label>
            <textarea
              value={persona.knowledge_notes}
              onChange={(e) =>
                setPersona({ ...persona, knowledge_notes: e.target.value })
              }
              placeholder="Add specific knowledge or context for the persona..."
              rows={6}
              className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
            />
          </div>
        </div>

        {/* Preview Section */}
        <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-6">
          <h3 className="text-sm font-semibold text-gray-200 mb-4">
            Persona Preview
          </h3>
          <div className="bg-[#0a0a0f] rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-fazle-600 flex items-center justify-center text-white text-xl font-bold">
                {persona.name?.[0]?.toUpperCase() || "A"}
              </div>
              <div>
                <p className="text-lg font-semibold text-gray-200">
                  {persona.name || "AI Persona"}
                </p>
                <p className="text-xs text-gray-500">
                  {persona.tone || "No tone set"} · {persona.language || "No language set"}
                </p>
              </div>
            </div>
            {persona.speaking_style && (
              <div className="pt-2 border-t border-gray-800">
                <p className="text-xs text-gray-500 mb-1">Speaking Style</p>
                <p className="text-sm text-gray-300 italic">
                  "{persona.speaking_style}"
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

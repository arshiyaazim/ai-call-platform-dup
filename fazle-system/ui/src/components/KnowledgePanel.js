"use client";

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";

export default function KnowledgePanel() {
  const { data: session } = useSession();
  const [text, setText] = useState("");
  const [source, setSource] = useState("manual");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState("text"); // "text", "url", "browse", "review"
  const [knowledgeItems, setKnowledgeItems] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");

  const authHeaders = useCallback(
    () => ({
      "Content-Type": "application/json",
      ...(session?.accessToken
        ? { Authorization: `Bearer ${session.accessToken}` }
        : {}),
    }),
    [session]
  );

  const loadActive = useCallback(async () => {
    try {
      const res = await fetch("/api/fazle/knowledge/active", { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setKnowledgeItems(data.items || []);
      }
    } catch {
      // silent
    }
  }, [authHeaders]);

  const searchKnowledge = async () => {
    if (!searchQuery.trim()) {
      loadActive();
      return;
    }
    try {
      const res = await fetch(`/api/fazle/knowledge/search?q=${encodeURIComponent(searchQuery)}`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setKnowledgeItems(data.items || []);
      }
    } catch {
      // silent
    }
  };

  useEffect(() => {
    if (mode === "browse" || mode === "review") loadActive();
  }, [mode, loadActive]);

  const ingestText = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/fazle/knowledge/ingest", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ text, source, title }),
      });
      if (res.ok) {
        const data = await res.json();
        setResult(data);
        setText("");
        setTitle("");
      } else {
        setResult({ error: "Failed to ingest" });
      }
    } catch {
      setResult({ error: "Service unavailable" });
    } finally {
      setLoading(false);
    }
  };

  const scrapeUrl = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/fazle/web/search", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ query: url, max_results: 1 }),
      });
      if (res.ok) {
        const data = await res.json();
        setResult({ status: "scraped", results: data.results });
      }
    } catch {
      setResult({ error: "Failed to scrape URL" });
    } finally {
      setLoading(false);
    }
  };

  const deprecateItem = async (itemId) => {
    try {
      await fetch("/api/fazle/knowledge/deprecate", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ knowledge_id: itemId, reason: "Deprecated via UI" }),
      });
      loadActive();
    } catch {
      // silent
    }
  };

  const archiveItem = async (itemId) => {
    try {
      await fetch("/api/fazle/knowledge/archive", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ knowledge_id: itemId, reason: "Archived via UI" }),
      });
      loadActive();
    } catch {
      // silent
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-gray-200">Knowledge Base</h2>
        <p className="text-xs text-gray-500">Upload, browse, and manage Fazle&apos;s knowledge</p>
      </div>

      <div className="p-4 border-b border-gray-800">
        <div className="flex gap-2 flex-wrap">
          {["text", "url", "browse", "review"].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === m ? "bg-fazle-600 text-white" : "bg-gray-800 text-gray-400"
              }`}
            >
              {m === "text" ? "Text / Document" : m === "url" ? "Web URL" : m === "browse" ? "Browse" : "Review"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {mode === "text" ? (
          <form onSubmit={ingestText} className="space-y-4">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Document title"
              className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
            />
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-fazle-500"
            >
              <option value="manual">Manual Input</option>
              <option value="document">Document</option>
              <option value="transcript">Voice Transcript</option>
            </select>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste text content here..."
              rows={12}
              className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-fazle-600 hover:bg-fazle-700 disabled:opacity-50 text-white py-3 rounded-lg text-sm font-medium"
            >
              {loading ? "Ingesting..." : "Ingest into Knowledge Base"}
            </button>
          </form>
        ) : mode === "url" ? (
          <form onSubmit={scrapeUrl} className="space-y-4">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/article"
              className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-fazle-600 hover:bg-fazle-700 disabled:opacity-50 text-white py-3 rounded-lg text-sm font-medium"
            >
              {loading ? "Processing..." : "Extract & Store"}
            </button>
          </form>
        ) : (
          /* Browse / Review mode */
          <div className="space-y-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchKnowledge()}
                placeholder="Search knowledge..."
                className="flex-1 bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500"
              />
              <button
                onClick={searchKnowledge}
                className="px-4 py-2 bg-fazle-600 hover:bg-fazle-700 text-white rounded-lg text-sm"
              >
                Search
              </button>
            </div>

            {knowledgeItems.length === 0 ? (
              <div className="text-center text-gray-500 py-8">No knowledge items found</div>
            ) : (
              <div className="space-y-3">
                {knowledgeItems.map((item) => (
                  <div
                    key={item.id}
                    className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-gray-200">
                            {item.key || item.category || "Untitled"}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs ${
                              item.status === "active"
                                ? "bg-green-900/50 text-green-300"
                                : item.status === "pending_review"
                                ? "bg-yellow-900/50 text-yellow-300"
                                : "bg-gray-700 text-gray-400"
                            }`}
                          >
                            {item.status}
                          </span>
                          {item.category && (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-900/30 text-blue-300">
                              {item.category}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-400 line-clamp-3">
                          {item.value || ""}
                        </p>
                        <div className="flex gap-4 mt-2 text-xs text-gray-500">
                          {item.source && <span>Source: {item.source}</span>}
                          {item.version && <span>v{item.version}</span>}
                          {item.confidence && <span>{Math.round(item.confidence * 100)}% confidence</span>}
                        </div>
                      </div>
                      <div className="flex gap-1 ml-3">
                        <button
                          onClick={() => deprecateItem(item.id)}
                          className="px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-900/30 rounded"
                          title="Deprecate"
                        >
                          Deprecate
                        </button>
                        <button
                          onClick={() => archiveItem(item.id)}
                          className="px-2 py-1 text-xs text-red-400 hover:bg-red-900/30 rounded"
                          title="Archive"
                        >
                          Archive
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="mt-6 bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-4">
            <h3 className="text-sm font-medium text-gray-200 mb-2">Result</h3>
            <pre className="text-xs text-gray-400 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

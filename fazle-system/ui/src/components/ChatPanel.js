"use client";

import { useState, useRef, useEffect } from "react";
import { useSession } from "next-auth/react";

export default function ChatPanel() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);
  const [conversationId, setConversationId] = useState(null);

  useEffect(() => {
    if (session?.user) {
      setMessages([
        {
          role: "assistant",
          content: `Hello ${session.user.name}. How can I help you today?`,
        },
      ]);
    }
  }, [session]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch("/api/fazle/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.accessToken
            ? { Authorization: `Bearer ${session.accessToken}` }
            : {}),
        },
        body: JSON.stringify({
          message: userMsg,
          conversation_id: conversationId,
          user: session?.user?.name || "User",
        }),
      });

      if (!res.ok) throw new Error("Request failed");

      const data = await res.json();
      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't process that. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-gray-200">
          Chat with Azim
        </h2>
        <p className="text-xs text-gray-500">
          Say &quot;Fazle, remember...&quot; to store preferences
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4 chat-container">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[70%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-fazle-600 text-white rounded-br-md"
                  : "bg-[#1a1a2e] text-gray-200 rounded-bl-md border border-gray-700/50"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#1a1a2e] text-gray-400 px-4 py-3 rounded-2xl rounded-bl-md border border-gray-700/50 text-sm">
              <span className="animate-pulse">Fazle is thinking...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <form
        onSubmit={sendMessage}
        className="border-t border-gray-800 p-4 flex gap-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Talk to Fazle..."
          className="flex-1 bg-[#1a1a2e] border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-fazle-600 hover:bg-fazle-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-3 rounded-xl text-sm font-medium transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
}

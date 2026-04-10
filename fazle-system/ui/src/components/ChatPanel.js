"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import ReactMarkdown from "react-markdown";

export default function ChatPanel() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [enableSearch, setEnableSearch] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    if (session?.user) {
      const greetings = {
        self: `What's on your mind?`,
        wife: `Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"} ${session.user.name}. How can I help you today?`,
        daughter: `Hey princess! What's up?`,
        son: `Hey buddy! What's going on?`,
        parent: `Assalamualaikum. How are you doing today?`,
        sibling: `Hey ${session.user.name}! What's up?`,
      };
      setMessages([
        {
          role: "assistant",
          content: greetings[session.user.relationship] || `Hello ${session.user.name}. How can I help you today?`,
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
    setSearchResults(null);

    try {
      // If search is enabled, run web search first
      let searchContext = "";
      if (enableSearch) {
        try {
          const searchRes = await fetch("/api/fazle/web/search", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {}),
            },
            body: JSON.stringify({ query: userMsg, max_results: 3 }),
          });
          if (searchRes.ok) {
            const searchData = await searchRes.json();
            setSearchResults(searchData.results || []);
            searchContext = (searchData.results || [])
              .map((r) => `[${r.title}]: ${r.snippet || r.content || ""}`)
              .join("\n");
          }
        } catch {}
      }

      const res = await fetch("/api/fazle/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {}),
        },
        body: JSON.stringify({
          message: searchContext ? `${userMsg}\n\n[Web search results]:\n${searchContext}` : userMsg,
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
        { role: "assistant", content: "Sorry, I couldn't process that. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const regenerateResponse = async () => {
    if (loading || messages.length < 2) return;
    const lastUserIdx = [...messages].reverse().findIndex((m) => m.role === "user");
    if (lastUserIdx === -1) return;
    const lastUserMsg = messages[messages.length - 1 - lastUserIdx];
    setMessages((prev) => prev.slice(0, prev.length - 1));
    setInput(lastUserMsg.content);
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await processFileUpload(file);
  };

  const processFileUpload = async (file) => {
    const isImage = /\.(png|jpg|jpeg|gif)$/i.test(file.name);
    // Show preview for images
    let previewUrl = null;
    if (isImage) {
      previewUrl = URL.createObjectURL(file);
    }
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: `📎 Uploading: ${file.name}...`,
        imagePreview: previewUrl,
      },
    ]);
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/fazle/files/upload", {
        method: "POST",
        headers: session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {},
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (isImage && data.caption) {
          updated[lastIdx] = {
            role: "user",
            content: `📷 ${data.filename}`,
            imagePreview: previewUrl,
            caption: data.caption,
          };
        } else {
          updated[lastIdx] = {
            role: "user",
            content: `📎 ${data.filename} (${(data.size / 1024).toFixed(1)}KB)${data.text_extracted ? " — text extracted and added to knowledge base" : ""}`,
          };
        }
        return updated;
      });
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "user", content: `📎 Upload failed: ${file.name}` };
        return updated;
      });
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Drag & drop handlers
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const allowed = ["pdf", "docx", "txt", "png", "jpg", "jpeg", "gif"];
        if (allowed.includes(ext)) {
          processFileUpload(file);
        }
      }
    },
    [session]
  );

  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const sizeKB = (blob.size / 1024).toFixed(0);
        setMessages((prev) => [
          ...prev,
          { role: "user", content: `🎙️ Transcribing voice message (${sizeKB}KB)...` },
        ]);
        setLoading(true);
        try {
          const formData = new FormData();
          formData.append("file", blob, "voice_message.webm");
          const headers = session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {};
          const res = await fetch("/api/fazle/files/upload", {
            method: "POST",
            headers,
            body: formData,
          });
          if (!res.ok) throw new Error("Transcription failed");
          const data = await res.json();
          const transcript = data.transcript || "";
          if (transcript) {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "user", content: `🎙️ "${transcript}"` };
              return updated;
            });
            // Send transcript as a chat message
            const chatRes = await fetch("/api/fazle/chat", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...(session?.accessToken ? { Authorization: `Bearer ${session.accessToken}` } : {}),
              },
              body: JSON.stringify({
                message: transcript,
                conversation_id: conversationId,
                user: session?.user?.name || "User",
              }),
            });
            if (chatRes.ok) {
              const chatData = await chatRes.json();
              setConversationId(chatData.conversation_id);
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: chatData.reply },
              ]);
            }
          } else {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "user",
                content: `🎙️ Voice message (${sizeKB}KB) — could not transcribe. Try again?`,
              };
              return updated;
            });
          }
        } catch {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "user",
              content: `🎙️ Voice message (${sizeKB}KB) — transcription failed`,
            };
            return updated;
          });
        } finally {
          setLoading(false);
        }
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      // Permission denied or not available
    }
  }, [isRecording]);

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div
      className="flex flex-col h-full relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-fazle-600/10 border-2 border-dashed border-fazle-500 rounded-xl flex items-center justify-center backdrop-blur-sm">
          <p className="text-fazle-300 text-lg font-medium">Drop image or file here</p>
        </div>
      )}

      {/* Image preview modal */}
      {previewImage && (
        <div
          className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setPreviewImage(null)}
        >
          <img
            src={previewImage}
            alt="Preview"
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      )}

      <div className="border-b border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-gray-200">Chat with Azim</h2>
        <p className="text-xs text-gray-500">
          Say &quot;Fazle, remember...&quot; to store preferences
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 chat-container">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] md:max-w-[70%] px-4 py-3 rounded-2xl text-sm leading-relaxed group relative ${
                msg.role === "user"
                  ? "bg-fazle-600 text-white rounded-br-md"
                  : "bg-[#1a1a2e] text-gray-200 rounded-bl-md border border-gray-700/50"
              }`}
            >
              {/* Image preview in user messages */}
              {msg.imagePreview && (
                <img
                  src={msg.imagePreview}
                  alt="Upload"
                  className="max-w-[200px] max-h-[200px] rounded-lg mb-2 cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={() => setPreviewImage(msg.imagePreview)}
                />
              )}
              {/* Caption under image */}
              {msg.caption && (
                <p className="text-xs text-white/70 italic mb-1">&quot;{msg.caption}&quot;</p>
              )}
              {msg.role === "assistant" ? (
                <div className="prose prose-invert prose-sm max-w-none [&_pre]:bg-[#0d0d14] [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:overflow-x-auto [&_code]:text-fazle-300 [&_a]:text-fazle-400">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <span>{msg.content}</span>
              )}
              {msg.role === "assistant" && (
                <button
                  onClick={() => copyToClipboard(msg.content)}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-gray-300 transition-opacity text-xs px-1.5 py-0.5 rounded bg-gray-800/50"
                  title="Copy"
                >
                  📋
                </button>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#1a1a2e] text-gray-400 px-4 py-3 rounded-2xl rounded-bl-md border border-gray-700/50 text-sm">
              <span className="animate-pulse">Azim is thinking...</span>
            </div>
          </div>
        )}
        {searchResults && searchResults.length > 0 && (
          <div className="flex justify-start">
            <div className="max-w-[85%] md:max-w-[70%]">
              <button
                onClick={() => setShowSearchResults(!showSearchResults)}
                className="text-xs text-fazle-400 hover:text-fazle-300 mb-1"
              >
                {showSearchResults ? "▼" : "▶"} {searchResults.length} web sources
              </button>
              {showSearchResults && (
                <div className="space-y-2">
                  {searchResults.map((r, idx) => (
                    <div key={idx} className="bg-[#1a1a2e] border border-gray-700/30 rounded-lg p-3 text-xs">
                      <p className="font-medium text-gray-300">{r.title}</p>
                      <p className="text-gray-500 mt-1 line-clamp-2">{r.snippet || r.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Toolbar */}
      <div className="border-t border-gray-800 px-4 pt-2 flex items-center gap-2">
        <button
          onClick={() => setEnableSearch(!enableSearch)}
          className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
            enableSearch
              ? "bg-fazle-600/20 text-fazle-300 border border-fazle-600/40"
              : "bg-gray-800 text-gray-500 hover:text-gray-300"
          }`}
          title="Toggle web search"
        >
          🔍 {enableSearch ? "Search ON" : "Search"}
        </button>
        {messages.length > 1 && !loading && (
          <button
            onClick={regenerateResponse}
            className="text-xs px-3 py-1.5 rounded-full bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
            title="Regenerate last response"
          >
            🔄 Regenerate
          </button>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={sendMessage}
        className="border-t border-gray-800/50 p-3 md:p-4 flex gap-2 md:gap-3 items-end"
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileUpload}
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.gif"
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="text-gray-500 hover:text-gray-300 transition-colors p-2 rounded-lg hover:bg-gray-800"
          title="Attach file"
          disabled={loading}
        >
          📎
        </button>
        <button
          type="button"
          onClick={toggleRecording}
          className={`p-2 rounded-lg transition-colors ${
            isRecording
              ? "text-red-400 bg-red-400/10 animate-pulse"
              : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
          }`}
          title={isRecording ? "Stop recording" : "Voice message"}
        >
          🎙️
        </button>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Talk to Azim..."
          className="flex-1 bg-[#1a1a2e] border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 transition-colors"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-fazle-600 hover:bg-fazle-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 md:px-6 py-3 rounded-xl text-sm font-medium transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
}

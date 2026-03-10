"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import {
  LiveKitRoom,
  useVoiceAssistant,
  BarVisualizer,
  RoomAudioRenderer,
  DisconnectButton,
} from "@livekit/components-react";
import "@livekit/components-styles";

function VoiceSession({ token, serverUrl, onDisconnect }) {
  return (
    <LiveKitRoom
      token={token}
      serverUrl={serverUrl}
      connect={true}
      audio={true}
      video={false}
      onDisconnected={onDisconnect}
      className="flex-1 flex flex-col"
    >
      <RoomAudioRenderer />
      <ActiveVoiceUI onDisconnect={onDisconnect} />
    </LiveKitRoom>
  );
}

function ActiveVoiceUI({ onDisconnect }) {
  const { state, audioTrack } = useVoiceAssistant();

  const statusLabels = {
    disconnected: "Disconnected",
    connecting: "Connecting...",
    initializing: "Starting up...",
    listening: "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-8 p-8">
      <div className="w-64 h-64 flex items-center justify-center">
        <BarVisualizer
          state={state}
          barCount={5}
          trackRef={audioTrack}
          className="w-full h-full"
          options={{ minHeight: 24 }}
        />
      </div>

      <div className="text-center space-y-2">
        <p className="text-2xl font-semibold text-gray-200">
          {statusLabels[state] || state}
        </p>
        <p className="text-sm text-gray-500">
          {state === "listening" && "Go ahead, I'm listening..."}
          {state === "thinking" && "Let me think about that..."}
          {state === "speaking" && ""}
        </p>
      </div>

      <DisconnectButton
        onClick={onDisconnect}
        className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl font-medium transition-colors"
      >
        End Call
      </DisconnectButton>
    </div>
  );
}

export default function VoicePanel() {
  const { data: session } = useSession();
  const [connectionState, setConnectionState] = useState("idle"); // idle | connecting | connected | error
  const [token, setToken] = useState(null);
  const [serverUrl, setServerUrl] = useState(null);
  const [error, setError] = useState(null);

  const startVoiceCall = useCallback(async () => {
    setConnectionState("connecting");
    setError(null);

    try {
      const res = await fetch("/api/fazle/voice/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.accessToken
            ? { Authorization: `Bearer ${session.accessToken}` }
            : {}),
        },
      });

      if (!res.ok) {
        throw new Error(`Failed to get voice token: ${res.status}`);
      }

      const data = await res.json();
      setToken(data.token);
      setServerUrl(data.url);
      setConnectionState("connected");
    } catch (err) {
      setError(err.message);
      setConnectionState("error");
    }
  }, [session]);

  const handleDisconnect = useCallback(() => {
    setToken(null);
    setServerUrl(null);
    setConnectionState("idle");
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-gray-200">
          Voice Call with Azim
        </h2>
        <p className="text-xs text-gray-500">
          Talk to Azim using your microphone
        </p>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center p-8">
        {connectionState === "idle" && (
          <div className="text-center space-y-6">
            <div className="w-32 h-32 mx-auto rounded-full bg-fazle-700/20 border-2 border-fazle-600/30 flex items-center justify-center">
              <span className="text-5xl">🎙️</span>
            </div>
            <div className="space-y-2">
              <p className="text-gray-300 text-lg">Ready to talk?</p>
              <p className="text-gray-500 text-sm">
                Press the button below to start a voice conversation
              </p>
            </div>
            <button
              onClick={startVoiceCall}
              className="px-8 py-4 bg-fazle-600 hover:bg-fazle-700 text-white rounded-xl font-medium text-lg transition-colors shadow-lg shadow-fazle-600/20"
            >
              Start Voice Call
            </button>
          </div>
        )}

        {connectionState === "connecting" && (
          <div className="text-center space-y-4">
            <div className="w-32 h-32 mx-auto rounded-full bg-fazle-700/20 border-2 border-fazle-600/30 flex items-center justify-center animate-pulse">
              <span className="text-5xl">📡</span>
            </div>
            <p className="text-gray-400">Connecting...</p>
          </div>
        )}

        {connectionState === "connected" && token && serverUrl && (
          <VoiceSession
            token={token}
            serverUrl={serverUrl}
            onDisconnect={handleDisconnect}
          />
        )}

        {connectionState === "error" && (
          <div className="text-center space-y-4">
            <div className="w-32 h-32 mx-auto rounded-full bg-red-900/20 border-2 border-red-600/30 flex items-center justify-center">
              <span className="text-5xl">⚠️</span>
            </div>
            <p className="text-red-400">{error}</p>
            <button
              onClick={startVoiceCall}
              className="px-6 py-3 bg-fazle-600 hover:bg-fazle-700 text-white rounded-xl font-medium transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

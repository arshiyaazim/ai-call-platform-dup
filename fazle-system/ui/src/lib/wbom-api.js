"use client";

import { useSession } from "next-auth/react";
import { useCallback } from "react";

const BASE = "/api/wbom";

export function useWbomApi() {
  const { data: session } = useSession();

  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    ...(session?.accessToken
      ? { Authorization: `Bearer ${session.accessToken}` }
      : {}),
  }), [session?.accessToken]);

  const request = useCallback(async (path, options = {}) => {
    const url = `${BASE}${path}`;
    const res = await fetch(url, {
      ...options,
      headers: { ...headers(), ...options.headers },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  }, [headers]);

  const get = useCallback((path) => request(path), [request]);

  const post = useCallback((path, body) =>
    request(path, { method: "POST", body: JSON.stringify(body) }),
  [request]);

  const put = useCallback((path, body) =>
    request(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  [request]);

  const del = useCallback((path) =>
    request(path, { method: "DELETE" }),
  [request]);

  return { get, post, put, del };
}

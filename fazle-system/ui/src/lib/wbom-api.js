"use client";

import { useSession } from "next-auth/react";
import { useCallback, useRef, useEffect, useState } from "react";
import { validateEnvelope, validateRows } from "./wbom-schemas";

const BASE = "/api/wbom";

// ── Universal WBOM API hook ──────────────────────────────────
// Handles: token management, standard envelope unwrap, error
// normalization, loading/error/empty states.
//
// Backend responses follow the envelope:
//   { success, data, meta, schema, version }
//
// useWbomList() auto-unwraps to { rows, meta, schema, ... }

export function useWbomApi() {
  const { data: session } = useSession();
  const tokenRef = useRef(session?.accessToken);

  useEffect(() => {
    tokenRef.current = session?.accessToken;
  }, [session?.accessToken]);

  const request = useCallback(async (path, options = {}) => {
    const url = `${BASE}${path}`;
    const hdrs = { "Content-Type": "application/json" };
    if (tokenRef.current) hdrs.Authorization = `Bearer ${tokenRef.current}`;
    const res = await fetch(url, {
      ...options,
      headers: { ...hdrs, ...options.headers },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  }, []);

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

  return { get, post, put, del, request };
}


// ── Unwrap standard envelope ─────────────────────────────────
// Handles both old (raw array) and new ({ success, data }) formats.
// Applies Zod validation when entity name is provided.

function unwrapList(json, entity = null) {
  if (json && json.success && Array.isArray(json.data)) {
    // Validate envelope structure
    try { validateEnvelope(json); } catch (e) {
      console.warn("[WBOM] Envelope validation failed:", e.message);
    }
    // Validate individual rows if entity is known
    let rows = json.data;
    if (entity) {
      const { valid } = validateRows(entity, rows);
      rows = valid;
    }
    return {
      rows,
      meta: json.meta || { total: rows.length, page: 1, count: rows.length },
      schema: json.schema || {},
    };
  }
  // Legacy: raw array response (backward compat)
  if (Array.isArray(json)) {
    let rows = json;
    if (entity) {
      const { valid } = validateRows(entity, rows);
      rows = valid;
    }
    return {
      rows,
      meta: { total: rows.length, page: 1, count: rows.length },
      schema: {},
    };
  }
  // Single object or other shape — wrap it
  return { rows: [], meta: { total: 0, page: 1, count: 0 }, schema: {} };
}


// ── useWbomList: fetch + unwrap + validate + state management ─
// Returns { rows, meta, schema, loading, error, reload }
// Pass entity name to enable Zod row validation:
//   useWbomList("/employees", [], "employees")

export function useWbomList(path, deps = [], entity = null) {
  const { get } = useWbomApi();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, count: 0 });
  const [schema, setSchema] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    get(path)
      .then((json) => {
        if (!mountedRef.current) return;
        const result = unwrapList(json, entity);
        setRows(result.rows);
        setMeta(result.meta);
        setSchema(result.schema);
      })
      .catch((err) => {
        if (!mountedRef.current) return;
        setError(err.message || "Failed to load data");
        setRows([]);
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [get, path, entity, ...deps]);

  useEffect(() => { reload(); }, [reload]);

  return { rows, meta, schema, loading, error, reload };
}


// ── useWbomCount: fetch a /count endpoint ────────────────────
// Works with both old { total: N } and new { success, data } formats.

export function useWbomCount(path) {
  const { get } = useWbomApi();
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    get(path)
      .then((json) => {
        if (!mounted) return;
        // Old format: { total: N }
        if (typeof json.total === "number") setTotal(json.total);
        // New wrapped: { success, data: { total: N } }
        else if (json.data && typeof json.data.total === "number") setTotal(json.data.total);
        else setTotal(0);
      })
      .catch(() => { if (mounted) setTotal(0); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [get, path]);

  return { total, loading };
}


// ── Label map for field names ────────────────────────────────
// Used by dynamic table and field auto-mapper components.

const LABEL_MAP = {
  id: "ID",
  name: "Name",
  phone: "Phone",
  salary: "Salary",
  designation: "Designation",
  status: "Status",
  joined: "Joined",
  bkash: "Bkash",
  nagad: "Nagad",
  nid: "NID",
  bank: "Bank Account",
  emergency_phone: "Emergency",
  address: "Address",
  employee_name: "Employee",
  employee_id: "Emp ID",
  employee_phone: "Emp Phone",
  type: "Type",
  amount: "Amount",
  method: "Method",
  date: "Date",
  time: "Time",
  reference: "Reference",
  remarks: "Remarks",
  company: "Company",
  balance: "Balance",
  terms: "Terms",
  is_active: "Active",
  position: "Position",
  experience: "Experience",
  source: "Source",
  applied_at: "Applied",
  event: "Event",
  actor: "Actor",
  entity: "Entity",
  entity_id: "Entity ID",
  payload: "Details",
  created_at: "Created",
  updated_at: "Updated",
};

export function fieldLabel(key) {
  return LABEL_MAP[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}


// ── Format cell value for display ────────────────────────────

export function formatCell(value, key) {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  // Dates
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}(T|$)/.test(value)) {
    try {
      const d = new Date(value);
      return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
    } catch { return value; }
  }
  // Currency-like fields
  if ((key === "amount" || key === "salary" || key === "balance") && typeof value === "number") {
    return `৳${value.toLocaleString()}`;
  }
  return String(value);
}

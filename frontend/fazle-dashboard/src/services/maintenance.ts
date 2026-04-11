import { apiGet, apiPost, apiPut, apiDelete } from './api';

// ── Types ──────────────────────────────────────────────────

export interface TableInfo {
  table_name: string;
  display_name: string;
  group: string;
  access_mode: string;
  singleton: boolean;
  description: string;
}

export interface ColumnSchema {
  name: string;
  display_name: string;
  type: string;
  required: boolean;
  max_length: number | null;
  enum_values: string[] | null;
  masked: boolean;
  immutable: boolean;
  searchable: boolean;
  default: string | null;
}

export interface TableSchema {
  table_name: string;
  display_name: string;
  group: string;
  access_mode: string;
  primary_key: string;
  pk_type: string;
  singleton: boolean;
  delete_policy: string;
  description: string;
  columns: ColumnSchema[];
  can_create: boolean;
  can_update: boolean;
  can_delete: boolean;
}

export interface RowsResponse {
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// ── Service ────────────────────────────────────────────────

const BASE = '/admin/maintenance';

export const maintenanceService = {
  listTables: () =>
    apiGet<{ tables: TableInfo[] }>(`${BASE}/tables`),

  getSchema: (tableName: string) =>
    apiGet<TableSchema>(`${BASE}/tables/${tableName}/schema`),

  listRows: (
    tableName: string,
    params?: { search?: string; page?: number; per_page?: number; sort_by?: string; sort_dir?: string }
  ) => {
    const qs = new URLSearchParams();
    if (params?.search) qs.set('search', params.search);
    if (params?.page) qs.set('page', String(params.page));
    if (params?.per_page) qs.set('per_page', String(params.per_page));
    if (params?.sort_by) qs.set('sort_by', params.sort_by);
    if (params?.sort_dir) qs.set('sort_dir', params.sort_dir);
    const q = qs.toString();
    return apiGet<RowsResponse>(`${BASE}/tables/${tableName}/rows${q ? `?${q}` : ''}`);
  },

  getRow: (tableName: string, rowId: string) =>
    apiGet<Record<string, unknown>>(`${BASE}/tables/${tableName}/rows/${rowId}`),

  createRow: (tableName: string, data: Record<string, unknown>) =>
    apiPost<Record<string, unknown>>(`${BASE}/tables/${tableName}/rows`, { data }),

  updateRow: (tableName: string, rowId: string, data: Record<string, unknown>) =>
    apiPut<Record<string, unknown>>(`${BASE}/tables/${tableName}/rows/${rowId}`, { data }),

  deleteRow: (tableName: string, rowId: string) =>
    apiDelete<{ status: string; policy: string }>(`${BASE}/tables/${tableName}/rows/${rowId}`),
};

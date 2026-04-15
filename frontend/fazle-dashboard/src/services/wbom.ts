import { apiGet, apiPost, apiPut, apiDelete } from './api';

// ── Types ────────────────────────────────────────────────────

export interface WbomEmployee {
  employee_id: number;
  employee_name: string;
  employee_mobile: string;
  designation: string;
  status: string;
  join_date?: string;
  created_at: string;
  updated_at: string;
}

export interface WbomContact {
  contact_id: number;
  contact_name: string;
  phone_number?: string;
  whatsapp_number?: string;
  company_name?: string;
  relation_type_id?: number;
  business_type_id?: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WbomProgram {
  program_id: number;
  contact_id?: number;
  employee_id?: number;
  mother_vessel: string;
  lighter_vessel?: string;
  shift?: string;
  status: string;
  start_date?: string;
  end_date?: string;
  created_at: string;
  updated_at: string;
  // joined fields
  employee_name?: string;
  contact_name?: string;
}

export interface WbomTransaction {
  transaction_id: number;
  employee_id: number;
  amount: number;
  payment_method: string;
  transaction_type: string;
  transaction_date: string;
  notes?: string;
  created_at: string;
  // joined
  employee_name?: string;
}

export interface WbomDailySummary {
  date: string;
  total_amount: number;
  transaction_count: number;
  by_method: Record<string, number>;
}

// The WBOM API base path (proxied through Next.js rewrite)
const W = '/wbom';

// ── Service ──────────────────────────────────────────────────

export const wbomService = {
  // ── Employees ──
  listEmployees: (params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomEmployee[]>(`${W}/employees${qs ? '?' + qs : ''}`);
  },
  getEmployee: (id: number) => apiGet<WbomEmployee>(`${W}/employees/${id}`),
  searchEmployees: (query: string) => apiGet<WbomEmployee[]>(`${W}/employees/search/${encodeURIComponent(query)}`),
  createEmployee: (data: Partial<WbomEmployee>) => apiPost<WbomEmployee>(`${W}/employees`, data),
  updateEmployee: (id: number, data: Partial<WbomEmployee>) => apiPut<WbomEmployee>(`${W}/employees/${id}`, data),
  deleteEmployee: (id: number) => apiDelete<void>(`${W}/employees/${id}`),

  // ── Contacts ──
  listContacts: (params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomContact[]>(`${W}/contacts${qs ? '?' + qs : ''}`);
  },
  searchContacts: (query: string) => apiGet<WbomContact[]>(`${W}/contacts/search/${encodeURIComponent(query)}`),
  createContact: (data: Partial<WbomContact>) => apiPost<WbomContact>(`${W}/contacts`, data),
  updateContact: (id: number, data: Partial<WbomContact>) => apiPut<WbomContact>(`${W}/contacts/${id}`, data),
  deleteContact: (id: number) => apiDelete<void>(`${W}/contacts/${id}`),

  // ── Escort Programs ──
  listPrograms: (params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomProgram[]>(`${W}/programs${qs ? '?' + qs : ''}`);
  },
  createProgram: (data: Partial<WbomProgram>) => apiPost<WbomProgram>(`${W}/programs`, data),
  updateProgram: (id: number, data: Partial<WbomProgram>) => apiPut<WbomProgram>(`${W}/programs/${id}`, data),
  deleteProgram: (id: number) => apiDelete<void>(`${W}/programs/${id}`),

  // ── Transactions ──
  listTransactions: (params?: { payment_method?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.payment_method) q.set('payment_method', params.payment_method);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomTransaction[]>(`${W}/transactions${qs ? '?' + qs : ''}`);
  },
  getDailySummary: (date: string) => apiGet<WbomDailySummary>(`${W}/transactions/daily-summary/${date}`),
  createTransaction: (data: Partial<WbomTransaction>) => apiPost<WbomTransaction>(`${W}/transactions`, data),
  deleteTransaction: (id: number) => apiDelete<void>(`${W}/transactions/${id}`),

  // ── Search ──
  quickSearch: (q: string, limit = 20) =>
    apiGet<unknown[]>(`${W}/search?q=${encodeURIComponent(q)}&limit=${limit}`),
};

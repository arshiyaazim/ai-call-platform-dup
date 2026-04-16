import { apiGet, apiPost, apiPut, apiDelete } from './api';

// ── Types ────────────────────────────────────────────────────

export interface WbomEmployee {
  employee_id: number;
  employee_name: string;
  employee_mobile: string;
  designation: string;
  status: string;
  joining_date?: string;
  bank_account?: string;
  emergency_contact?: string;
  address?: string;
  created_at: string;
  updated_at: string;
  // detail fields (from /detail endpoint)
  programs?: WbomProgram[];
  transactions?: WbomTransaction[];
  total_programs?: number;
  total_transactions?: number;
  total_amount?: number;
}

export interface WbomContact {
  contact_id: number;
  display_name: string;
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
  escort_employee_id?: number;
  mother_vessel: string;
  lighter_vessel?: string;
  master_mobile?: string;
  destination?: string;
  escort_mobile?: string;
  shift?: string;
  status: string;
  program_date?: string;
  assignment_time?: string;
  completion_time?: string;
  remarks?: string;
  created_at?: string;
  // joined fields
  employee_name?: string;
  employee_mobile?: string;
}

export interface WbomTransaction {
  transaction_id: number;
  employee_id: number;
  program_id?: number;
  amount: number | string;
  payment_method: string;
  payment_mobile?: string;
  transaction_type: string;
  transaction_date: string;
  transaction_time?: string;
  status?: string;
  reference_number?: string;
  remarks?: string;
  // joined
  employee_name?: string;
  employee_mobile?: string;
}

export interface WbomDailySummary {
  date: string;
  total_amount: number;
  transaction_count: number;
  by_method: Record<string, number>;
}

export interface SearchSuggestion {
  type: 'employee' | 'vessel' | 'lighter';
  id: number | null;
  label: string;
  sublabel: string;
  status: string | null;
}

export interface FullSearchResult {
  query: string;
  type: string;
  employees: (WbomEmployee & {
    programs?: WbomProgram[];
    transactions?: WbomTransaction[];
    total_programs?: number;
    total_transactions?: number;
    total_amount?: number;
  })[];
  vessel_programs: (WbomProgram & {
    employee_name?: string;
    employee_mobile?: string;
    designation?: string;
  })[];
}

export interface CountResult {
  total: number;
}

// The WBOM API base path (proxied through Next.js rewrite → nginx → WBOM:9900)
const W = '/wbom';

// ── Service ──────────────────────────────────────────────────

export const wbomService = {
  // ── Employees ──
  listEmployees: (params?: { status?: string; designation?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.designation) q.set('designation', params.designation);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomEmployee[]>(`${W}/employees${qs ? '?' + qs : ''}`);
  },
  countEmployees: (params?: { status?: string; designation?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.designation) q.set('designation', params.designation);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/employees/count${qs ? '?' + qs : ''}`);
  },
  getEmployee: (id: number) => apiGet<WbomEmployee>(`${W}/employees/${id}`),
  getEmployeeDetail: (id: number) => apiGet<WbomEmployee>(`${W}/employees/${id}/detail`),
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
  listPrograms: (params?: { status?: string; shift?: string; date_from?: string; date_to?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.shift) q.set('shift', params.shift);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomProgram[]>(`${W}/programs${qs ? '?' + qs : ''}`);
  },
  countPrograms: (params?: { status?: string; date_from?: string; date_to?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/programs/count${qs ? '?' + qs : ''}`);
  },
  createProgram: (data: Partial<WbomProgram>) => apiPost<WbomProgram>(`${W}/programs`, data),
  updateProgram: (id: number, data: Partial<WbomProgram>) => apiPut<WbomProgram>(`${W}/programs/${id}`, data),
  deleteProgram: (id: number) => apiDelete<void>(`${W}/programs/${id}`),

  // ── Transactions ──
  listTransactions: (params?: { transaction_type?: string; payment_method?: string; date_from?: string; date_to?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.transaction_type) q.set('transaction_type', params.transaction_type);
    if (params?.payment_method) q.set('payment_method', params.payment_method);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomTransaction[]>(`${W}/transactions${qs ? '?' + qs : ''}`);
  },
  countTransactions: (params?: { transaction_type?: string; payment_method?: string; date_from?: string; date_to?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.transaction_type) q.set('transaction_type', params.transaction_type);
    if (params?.payment_method) q.set('payment_method', params.payment_method);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/transactions/count${qs ? '?' + qs : ''}`);
  },
  getDailySummary: (date: string) => apiGet<WbomDailySummary>(`${W}/transactions/daily-summary/${date}`),
  createTransaction: (data: Partial<WbomTransaction>) => apiPost<WbomTransaction>(`${W}/transactions`, data),
  deleteTransaction: (id: number) => apiDelete<void>(`${W}/transactions/${id}`),

  // ── Search ──
  suggest: (q: string, limit = 8) =>
    apiGet<SearchSuggestion[]>(`${W}/search/suggest?q=${encodeURIComponent(q)}&limit=${limit}`),
  fullSearch: (q: string, type?: string) => {
    const params = new URLSearchParams({ q });
    if (type) params.set('type', type);
    return apiGet<FullSearchResult>(`${W}/search/full?${params.toString()}`);
  },
  countEmployees: (params?: { status?: string; designation?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.designation) q.set('designation', params.designation);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/employees/count${qs ? '?' + qs : ''}`);
  },
  getEmployee: (id: number) => apiGet<WbomEmployee>(`${W}/employees/${id}`),
  getEmployeeDetail: (id: number) => apiGet<WbomEmployee>(`${W}/employees/${id}/detail`),
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
  listPrograms: (params?: { status?: string; shift?: string; date_from?: string; date_to?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.shift) q.set('shift', params.shift);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomProgram[]>(`${W}/programs${qs ? '?' + qs : ''}`);
  },
  countPrograms: (params?: { status?: string; date_from?: string; date_to?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/programs/count${qs ? '?' + qs : ''}`);
  },
  createProgram: (data: Partial<WbomProgram>) => apiPost<WbomProgram>(`${W}/programs`, data),
  updateProgram: (id: number, data: Partial<WbomProgram>) => apiPut<WbomProgram>(`${W}/programs/${id}`, data),
  deleteProgram: (id: number) => apiDelete<void>(`${W}/programs/${id}`),

  // ── Transactions ──
  listTransactions: (params?: { transaction_type?: string; payment_method?: string; date_from?: string; date_to?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.transaction_type) q.set('transaction_type', params.transaction_type);
    if (params?.payment_method) q.set('payment_method', params.payment_method);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<WbomTransaction[]>(`${W}/transactions${qs ? '?' + qs : ''}`);
  },
  countTransactions: (params?: { transaction_type?: string; payment_method?: string; date_from?: string; date_to?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.transaction_type) q.set('transaction_type', params.transaction_type);
    if (params?.payment_method) q.set('payment_method', params.payment_method);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/transactions/count${qs ? '?' + qs : ''}`);
  },
  getDailySummary: (date: string) => apiGet<WbomDailySummary>(`${W}/transactions/daily-summary/${date}`),
  createTransaction: (data: Partial<WbomTransaction>) => apiPost<WbomTransaction>(`${W}/transactions`, data),
  deleteTransaction: (id: number) => apiDelete<void>(`${W}/transactions/${id}`),

  // ── Search ──
  suggest: (q: string, limit = 8) =>
    apiGet<SearchSuggestion[]>(`${W}/search/suggest?q=${encodeURIComponent(q)}&limit=${limit}`),
  fullSearch: (q: string, type?: string) => {
    const params = new URLSearchParams({ q });
    if (type) params.set('type', type);
    return apiGet<FullSearchResult>(`${W}/search/full?${params.toString()}`);
  },
  quickSearch: (q: string, limit = 20) =>
    apiGet<unknown[]>(`${W}/search?q=${encodeURIComponent(q)}&limit=${limit}`),
};

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
  bkash_number?: string;
  nagad_number?: string;
  basic_salary?: number;
  nid_number?: string;
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
  start_date?: string;
  end_date?: string;
  end_shift?: string;
  release_point?: string;
  day_count?: number;
  conveyance?: number;
  capacity?: string;
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

// ── New types for payroll automation ─────────────────────────

export interface WbomSalaryRecord {
  salary_id: number;
  employee_id: number;
  month: number;
  year: number;
  basic_salary?: number;
  total_programs: number;
  program_allowance?: number;
  other_allowance?: number;
  total_advances?: number;
  total_deductions?: number;
  net_salary?: number;
  status: string;
  remarks?: string;
  employee_name?: string;
  designation?: string;
}

export interface WbomAttendance {
  attendance_id: number;
  employee_id: number;
  attendance_date: string;
  status: string;
  location?: string;
  check_in_time?: string;
  check_out_time?: string;
  remarks?: string;
  recorded_by?: string;
  created_at: string;
  employee_name?: string;
  designation?: string;
  employee_mobile?: string;
}

export interface WbomEmployeeRequest {
  request_id: number;
  employee_id: number;
  request_type: string;
  message_body?: string;
  sender_number?: string;
  status: string;
  response_text?: string;
  delay_hours: number;
  created_at: string;
  responded_at?: string;
  employee_name?: string;
  designation?: string;
  employee_mobile?: string;
}

export interface AdminCommandResult {
  command_type: string;
  result: Record<string, unknown>;
  message: string;
  requires_confirmation: boolean;
}

export interface FuzzySearchResult {
  employee_id: number;
  employee_name: string;
  employee_mobile: string;
  designation: string;
  status: string;
  similarity: number;
  bkash_number?: string;
  nagad_number?: string;
}

// The WBOM API base path (proxied through Next.js rewrite → nginx → WBOM:9900)
const W = '/wbom';

// ── Master Contact types ─────────────────────────────────────

export interface MasterContact {
  id: number;
  canonical_phone: string;
  display_name: string;
  role: string;
  sub_role: string;
  source: string;
  is_whatsapp: boolean;
  employee_id?: number;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MessageHistoryItem {
  id: number;
  canonical_phone: string;
  platform: string;
  direction: string;
  message_text: string;
  wa_message_id?: string;
  role_snapshot: string;
  created_at: string;
  display_name?: string;
  role?: string;
}

export interface RoleCount {
  role: string;
  count: number;
}

export interface UnifiedSearchResult {
  contacts: MasterContact[];
  employees: WbomEmployee[];
  messages: MessageHistoryItem[];
}

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
  quickSearch: (q: string, limit = 20) =>
    apiGet<unknown[]>(`${W}/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  // ── Fuzzy Search ──
  fuzzySearch: (q: string, limit = 5) =>
    apiGet<FuzzySearchResult[]>(`${W}/search/fuzzy?q=${encodeURIComponent(q)}&limit=${limit}`),

  // ── Salary ──
  generateSalary: (data: { employee_id: number; month: number; year: number; basic_salary: number; program_allowance?: number; other_allowance?: number; remarks?: string }) =>
    apiPost<WbomSalaryRecord>(`${W}/salary/generate`, data),
  getSalarySummary: (month: number, year: number) =>
    apiGet<{ month: number; year: number; records: WbomSalaryRecord[]; total_payable: number }>(`${W}/salary/summary?month=${month}&year=${year}`),
  markSalaryPaid: (salaryId: number) =>
    apiPost<{ paid: boolean }>(`${W}/salary/mark-paid/${salaryId}`, {}),

  // ── Attendance ──
  recordAttendance: (data: { employee_id: number; attendance_date: string; status: string; location?: string; remarks?: string; recorded_by?: string }) =>
    apiPost<{ action: string; attendance_id: number }>(`${W}/attendance/`, data),
  bulkAttendance: (status: string, date?: string, recorded_by?: string) => {
    const q = new URLSearchParams({ status });
    if (date) q.set('attendance_date', date);
    if (recorded_by) q.set('recorded_by', recorded_by);
    return apiPost<{ marked: number; skipped: number; date: string }>(`${W}/attendance/bulk?${q.toString()}`, {});
  },
  getAttendanceReport: (params?: { attendance_date?: string; employee_id?: number }) => {
    const q = new URLSearchParams();
    if (params?.attendance_date) q.set('attendance_date', params.attendance_date);
    if (params?.employee_id) q.set('employee_id', String(params.employee_id));
    const qs = q.toString();
    return apiGet<WbomAttendance[]>(`${W}/attendance/report${qs ? '?' + qs : ''}`);
  },
  getMonthlyAttendanceSummary: (employeeId: number, month: number, year: number) =>
    apiGet<Record<string, number>>(`${W}/attendance/monthly-summary/${employeeId}?month=${month}&year=${year}`),

  // ── Admin Commands ──
  sendAdminCommand: (sender_number: string, message_body: string) =>
    apiPost<AdminCommandResult>(`${W}/admin/command`, { sender_number, message_body }),
  createPaymentDraft: (data: { employee_id: number; amount: number; payment_method: string; transaction_type?: string }) =>
    apiPost<{ draft_message: string; employee: Record<string, unknown>; ready_to_send: boolean }>(`${W}/admin/payment-draft`, data),
  getSalaryDrafts: (month: number, year: number) =>
    apiGet<{ employee_id: number; employee_name: string; net_salary: number; draft_message: string }[]>(`${W}/admin/salary-drafts?month=${month}&year=${year}`),
  getDailyPaymentSummary: (date?: string) => {
    const q = date ? `?target_date=${date}` : '';
    return apiGet<{ date: string; transactions: unknown[]; total: number; by_type: Record<string, number> }>(`${W}/admin/daily-summary${q}`);
  },

  // ── Employee Self-Service ──
  getPendingRequests: (limit = 50) =>
    apiGet<WbomEmployeeRequest[]>(`${W}/self-service/requests?limit=${limit}`),
  respondToRequest: (requestId: number, response_text: string, status = 'Responded') =>
    apiPost<{ success: boolean }>(`${W}/self-service/requests/${requestId}/respond?response_text=${encodeURIComponent(response_text)}&status=${status}`, {}),

  // ── Master Contacts ──
  listMasterContacts: (params?: { role?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.role) q.set('role', params.role);
    if (params?.search) q.set('search', params.search);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<MasterContact[]>(`${W}/master/contacts${qs ? '?' + qs : ''}`);
  },
  countMasterContacts: (params?: { role?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.role) q.set('role', params.role);
    if (params?.search) q.set('search', params.search);
    const qs = q.toString();
    return apiGet<CountResult>(`${W}/master/contacts/count${qs ? '?' + qs : ''}`);
  },
  getMasterContact: (phone: string) =>
    apiGet<MasterContact>(`${W}/master/contacts/${encodeURIComponent(phone)}`),
  updateMasterContact: (phone: string, data: Partial<MasterContact>) =>
    apiPut<MasterContact>(`${W}/master/contacts/${encodeURIComponent(phone)}`, data),
  createMasterContact: (data: { phone: string; display_name?: string; role?: string; sub_role?: string; source?: string; is_whatsapp?: boolean }) =>
    apiPost<MasterContact>(`${W}/master/contacts`, data),
  setContactRole: (phone: string, role: string) =>
    apiPut<MasterContact>(`${W}/master/contacts/${encodeURIComponent(phone)}/role?role=${encodeURIComponent(role)}`, {}),

  // ── Roles ──
  listRoles: () => apiGet<RoleCount[]>(`${W}/master/roles`),

  // ── Message History ──
  getMessageHistory: (phone: string, params?: { limit?: number; offset?: number; platform?: string }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    if (params?.platform) q.set('platform', params.platform);
    const qs = q.toString();
    return apiGet<{ messages: MessageHistoryItem[]; total: number; phone: string }>(`${W}/master/messages/${encodeURIComponent(phone)}${qs ? '?' + qs : ''}`);
  },
  listRecentMessages: (params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiGet<MessageHistoryItem[]>(`${W}/master/messages${qs ? '?' + qs : ''}`);
  },

  // ── Unified Search ──
  unifiedSearch: (query: string, limit = 20) =>
    apiGet<UnifiedSearchResult>(`${W}/master/search?q=${encodeURIComponent(query)}&limit=${limit}`),
};

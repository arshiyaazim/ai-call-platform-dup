/* ── Ops-specific fetch helpers (route through /api/ops, not /api/fazle) ── */
const OPS_BASE = '/api/ops';

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('fazle_token') : null;
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function opsGet<T>(path: string): Promise<T> {
  const res = await fetch(`${OPS_BASE}${path}`, { method: 'GET', headers: getAuthHeaders() });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.json();
}

async function opsPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${OPS_BASE}${path}`, {
    method: 'POST', headers: getAuthHeaders(), body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.json();
}

async function opsPut<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${OPS_BASE}${path}`, {
    method: 'PUT', headers: getAuthHeaders(), body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.json();
}

async function opsDownload(path: string): Promise<Blob> {
  const res = await fetch(`${OPS_BASE}${path}`, { method: 'GET', headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Export failed');
  return res.blob();
}

/* ── Types ── */

export interface OpsEmployee { id: number; employee_id: string; name: string; mobile: string; role: string; }
export interface OpsProgram { id: number; mother_vessel: string; lighter_vessel?: string; destination?: string; escort_name?: string; escort_mobile?: string; start_date?: string; end_date?: string; shift?: string; status: string; food?: number; transport?: number; total_cost?: number; date?: string; }
export interface OpsPayment { id: number; employee_id: string; name: string; amount: number; method: string; status: string; category?: string; program_id?: number; paid_by?: string; payment_date?: string; }
export interface OpsAttendance { id: number; employee_id: string; name: string; location?: string; client_name?: string; date: string; shift?: string; }
export interface OpsNote { id: number; entity_type: string; entity_id: string; note: string; }
export interface OpsSummary { running_programs: number; completed_programs: number; running_payments: string; completed_payments: string; total_employees: number; today_attendance: number; completed_today: number; pending_duties: number; top_vessels: { mother_vessel: string; trip_count: string; total_cost: string }[]; today_payments: { total: string; count: number }; active_alerts: number; }
export interface SearchResult { employees?: OpsEmployee[]; programs?: OpsProgram[]; payments?: OpsPayment[]; }
export interface TypeaheadResult { suggestions: string[]; }

export interface EmployeePaymentSummary { total_transactions: string; grand_total: string; food_total: string; transport_total: string; general_total: string; salary_total: string; advance_total: string; earliest_date: string; latest_date: string; }
export interface EmployeePaymentHistory { employee: { employee_id: string; name: string | null; mobile: string | null; role: string | null }; summary: EmployeePaymentSummary; transactions: (OpsPayment & { mother_vessel?: string })[]; }

export interface VesselBilling { mother_vessel: string; total_trips: string; total_escorts: string; total_food: string; total_transport: string; total_cost: string; first_trip: string; last_trip: string; running_count: string; completed_count: string; }
export interface EmployeeSalary { employee_id: string; name: string; duty_days: number; daily_rate: number; calculated_salary: number; food_total: number; transport_total: number; salary_paid: number; advance_total: number; total_paid: number; net_due: number; }
export interface OpsAlert { type: string; severity: 'high' | 'medium' | 'low'; title: string; description: string; entity_id?: number | string; entity_type?: string; data?: Record<string, any>; }
export interface OpsRate { id: number; rate_type: string; destination?: string; amount: number; effective_from: string; active: boolean; }

/* ── Service ── */

export const opsService = {
  /* Dashboard */
  getSummary: () =>
    opsGet<OpsSummary>('/dashboard/summary'),

  /* Employees */
  listEmployees: (params?: { role?: string; q?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<OpsEmployee[]>(`/employees${qs ? '?' + qs : ''}`);
  },
  createEmployee: (data: { employee_id: string; name: string; role?: string }) =>
    opsPost<OpsEmployee>('/employees', data),
  updateEmployee: (id: number, data: Partial<OpsEmployee>) =>
    opsPut<OpsEmployee>(`/employees/${id}`, data),

  /* Programs */
  listPrograms: (params?: { status?: string; vessel?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<OpsProgram[]>(`/programs${qs ? '?' + qs : ''}`);
  },
  createProgram: (data: Partial<OpsProgram>) =>
    opsPost<OpsProgram>('/programs', data),
  completeProgram: (id: number) =>
    opsPost<OpsProgram>(`/programs/${id}/complete`, {}),

  /* Payments */
  listPayments: (params?: { status?: string; employee_id?: string; from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<OpsPayment[]>(`/payments${qs ? '?' + qs : ''}`);
  },
  createPayment: (data: { employee_id: string; amount: number; method?: string; payment_date?: string }) =>
    opsPost<OpsPayment>('/payments', data),
  completePayment: (id: number) =>
    opsPost<OpsPayment>(`/payments/${id}/complete`, {}),
  paymentSummary: () =>
    opsGet<{ running_total: string; completed_total: string; running_count: string; completed_count: string }>('/payments/summary'),
  employeePaymentHistory: (employeeId: string, params?: { from?: string; to?: string; status?: string }) => {
    const qs = params ? new URLSearchParams(params as Record<string, string>).toString() : '';
    return opsGet<EmployeePaymentHistory>(`/payments/employee/${employeeId}${qs ? '?' + qs : ''}`);
  },

  /* Attendance */
  listAttendance: (params?: { employee_id?: string; date?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<OpsAttendance[]>(`/attendance${qs ? '?' + qs : ''}`);
  },
  recordAttendance: (data: { employee_id: string; location?: string; client_name?: string }) =>
    opsPost<OpsAttendance>('/attendance', data),

  /* Search */
  search: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return opsGet<SearchResult>(`/search?${qs}`);
  },
  typeahead: (q: string) =>
    opsGet<TypeaheadResult>(`/search/suggest?q=${encodeURIComponent(q)}`),

  /* Notes */
  listNotes: (entityType: string, entityId: string) =>
    opsGet<OpsNote[]>(`/notes?entity_type=${entityType}&entity_id=${entityId}`),
  createNote: (data: { entity_type: string; entity_id: string; content: string }) =>
    opsPost<OpsNote>('/notes', data),

  /* WhatsApp simulate (for chat panel testing) */
  simulateMessage: (text: string, senderId: string = 'dashboard') =>
    opsPost<{ handled: boolean; reply?: string; intent?: string }>('/whatsapp/process', {
      sender_id: senderId,
      text,
    }),

  /* ── Business Intelligence ── */

  /* Billing */
  getBillingVesselSummary: (params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<{ vessels: VesselBilling[]; count: number }>(`/billing/vessel-summary${qs ? '?' + qs : ''}`);
  },
  getBillingVesselDetail: (vessel: string, params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<{ vessel: string; programs: OpsProgram[]; payments: OpsPayment[] }>(
      `/billing/vessel/${encodeURIComponent(vessel)}${qs ? '?' + qs : ''}`
    );
  },

  /* Salary */
  getSalarySummary: (params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<{ employees: EmployeeSalary[]; count: number; daily_rate: number }>(`/salary/employee-summary${qs ? '?' + qs : ''}`);
  },
  getSalaryDetail: (employeeId: string, params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsGet<EmployeeSalary & { attendance: OpsAttendance[]; payments: OpsPayment[]; programs: OpsProgram[] }>(
      `/salary/employee/${encodeURIComponent(employeeId)}${qs ? '?' + qs : ''}`
    );
  },
  getRates: () => opsGet<{ rates: OpsRate[] }>('/salary/rates'),
  updateRate: (id: number, data: { amount?: number; active?: boolean }) =>
    opsPut<OpsRate>(`/salary/rates/${id}`, data),

  /* Alerts */
  getAllAlerts: (days?: number) =>
    opsGet<{ alerts: OpsAlert[]; count: number; summary: { high: number; medium: number; low: number } }>(
      `/alerts/all${days ? '?days=' + days : ''}`
    ),
  getPendingDuties: (days?: number) =>
    opsGet<{ alerts: OpsAlert[]; count: number }>(
      `/alerts/pending-duties${days ? '?days=' + days : ''}`
    ),
  getPaymentIssues: () =>
    opsGet<{ alerts: OpsAlert[]; count: number }>('/alerts/payment-issues'),

  /* Export */
  exportPrograms: (params?: { from?: string; to?: string; status?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsDownload(`/export/programs${qs ? '?' + qs : ''}`);
  },
  exportPayments: (params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsDownload(`/export/payments${qs ? '?' + qs : ''}`);
  },
  exportSalary: (params?: { from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return opsDownload(`/export/salary${qs ? '?' + qs : ''}`);
  },
};

import { apiGet, apiPost } from './api';

export interface GdprRequest {
  id: string;
  request_type: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  error_message?: string;
  retry_count?: number;
}

export interface UserConsent {
  terms_accepted: boolean;
  privacy_accepted: boolean;
  accepted_at: string | null;
}

export interface UserDataExport {
  status: string;
  request_id: string;
  message: string;
}

export interface ExportStatus {
  status: string;
  download_token?: string;
  password?: string;
  expires_in_hours?: number;
  message: string;
}

export interface GdprStats {
  total_requests: number;
  completed: number;
  failed: number;
  pending: number;
  total_deletions: number;
  total_exports: number;
  total_fb_deletions: number;
  avg_completion_secs: number | null;
  pending_permanent_deletions: number;
  export_store_size: number;
}

export interface AdminRequestsResponse {
  requests: GdprRequest[];
  total: number;
}

export interface UserIdentity {
  user_id: string;
  email: string | null;
  facebook_id: string | null;
  whatsapp_id: string | null;
  phone_number: string | null;
}

export const gdprService = {
  // ── User Endpoints ──
  getMyData: () => apiGet<Record<string, unknown>>('/gdpr/me'),

  exportMyData: () => apiPost<UserDataExport>('/gdpr/export'),

  getExportStatus: (requestId: string) =>
    apiGet<ExportStatus>(`/gdpr/export/${requestId}`),

  deleteMyData: () =>
    apiPost<{ status: string; message: string; request_id: string; grace_period_days: number }>('/gdpr/delete'),

  cancelDeletion: () =>
    apiPost<{ status: string; message: string }>('/gdpr/cancel-deletion'),

  getRequests: () => apiGet<{ requests: GdprRequest[] }>('/gdpr/status'),

  getConsent: () => apiGet<UserConsent>('/gdpr/consent'),

  saveConsent: (terms: boolean, privacy: boolean) =>
    apiPost<{ status: string; consent: UserConsent }>('/gdpr/consent', { terms, privacy }),

  getIdentity: () => apiGet<UserIdentity>('/gdpr/identity'),

  updateIdentity: (data: { facebook_id?: string; whatsapp_id?: string; phone_number?: string }) =>
    apiPost<{ status: string; identity: UserIdentity }>('/gdpr/identity', data),

  // ── Admin Endpoints ──
  adminGetRequests: (limit = 50, offset = 0, status?: string) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    return apiGet<AdminRequestsResponse>(`/gdpr/admin/requests?${params}`);
  },

  adminGetStats: () => apiGet<GdprStats>('/gdpr/admin/stats'),

  adminRetryFailed: () =>
    apiPost<{ status: string; message: string }>('/gdpr/admin/retry-failed'),

  adminProcessDeletions: () =>
    apiPost<{ status: string; message: string }>('/gdpr/admin/process-deletions'),

  adminCleanupExports: () =>
    apiPost<{ cleaned: number; remaining: number }>('/gdpr/admin/cleanup-exports'),
};

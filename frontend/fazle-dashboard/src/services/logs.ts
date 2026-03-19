import { apiGet, apiDelete } from './api';
import type { LogEntry } from '@/types';

export const logService = {
  list: () => apiGet<LogEntry[]>('/admin/logs'),
  delete: (id: string) => apiDelete(`/admin/logs/${id}`),
};

import { apiGet, apiPut, apiPatch, apiDelete } from './api';
import type { Memory } from '@/types';

export const memoryService = {
  list: () => apiGet<Memory[]>('/admin/memories'),
  update: (id: string, data: Partial<Memory>) => apiPut<Memory>(`/memory/${id}`, data),
  toggleLock: (id: string) => apiPatch<Memory>(`/memory/${id}/lock`),
  delete: (id: string) => apiDelete(`/admin/memories/${id}`),
};

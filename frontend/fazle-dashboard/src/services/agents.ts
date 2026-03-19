import { apiGet, apiPost, apiPut, apiDelete } from './api';
import type { Agent } from '@/types';

export const agentService = {
  list: () => apiGet<Agent[]>('/admin/agents'),
  create: (data: Omit<Agent, 'id'>) => apiPost<Agent>('/admin/agents', data),
  update: (id: string, data: Partial<Agent>) => apiPut<Agent>(`/admin/agents/${id}`, data),
  delete: (id: string) => apiDelete(`/admin/agents/${id}`),
};

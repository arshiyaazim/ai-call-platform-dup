import { apiGet, apiPost, apiPut, apiDelete } from './api';
import type { Task } from '@/types';

export const taskService = {
  list: () => apiGet<Task[]>('/admin/tasks'),
  create: (data: Omit<Task, 'id' | 'last_run' | 'next_run'>) => apiPost<Task>('/admin/tasks', data),
  update: (id: string, data: Partial<Task>) => apiPut<Task>(`/admin/tasks/${id}`, data),
  delete: (id: string) => apiDelete(`/admin/tasks/${id}`),
};

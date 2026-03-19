import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from './api';
import type { Plugin } from '@/types';

export const pluginService = {
  list: () => apiGet<Plugin[]>('/admin/plugins'),
  install: (file: File) => apiUpload<Plugin>('/admin/plugins/install', file),
  update: (id: string, data: Partial<Plugin>) => apiPut<Plugin>(`/admin/plugins/${id}`, data),
  delete: (id: string) => apiDelete(`/admin/plugins/${id}`),
};

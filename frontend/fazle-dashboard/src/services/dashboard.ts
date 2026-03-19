import { apiGet } from './api';
import type { DashboardStats } from '@/types';

export const dashboardService = {
  stats: () => apiGet<DashboardStats>('/admin/dashboard/stats'),
};

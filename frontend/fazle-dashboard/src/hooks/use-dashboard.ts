import { useQuery } from '@tanstack/react-query';
import { dashboardService } from '@/services/dashboard';

export function useDashboardStats() {
  return useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: dashboardService.stats,
    refetchInterval: 30000,
  });
}

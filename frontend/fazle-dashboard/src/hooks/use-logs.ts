import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { logService } from '@/services/logs';

export function useLogs() {
  return useQuery({
    queryKey: ['logs'],
    queryFn: logService.list,
  });
}

export function useDeleteLog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => logService.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['logs'] }),
  });
}

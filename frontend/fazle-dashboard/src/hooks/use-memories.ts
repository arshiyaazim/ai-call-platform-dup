import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memoryService } from '@/services/memory';
import type { Memory } from '@/types';

export function useMemories() {
  return useQuery({
    queryKey: ['memories'],
    queryFn: memoryService.list,
  });
}

export function useUpdateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Memory> }) =>
      memoryService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memories'] }),
  });
}

export function useToggleMemoryLock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => memoryService.toggleLock(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memories'] }),
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => memoryService.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memories'] }),
  });
}

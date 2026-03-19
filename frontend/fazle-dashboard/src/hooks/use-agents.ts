import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentService } from '@/services/agents';
import type { Agent } from '@/types';

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: agentService.list,
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<Agent, 'id'>) => agentService.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Agent> }) =>
      agentService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => agentService.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  });
}

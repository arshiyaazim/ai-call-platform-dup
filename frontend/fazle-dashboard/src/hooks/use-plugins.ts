import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { pluginService } from '@/services/plugins';
import type { Plugin } from '@/types';

export function usePlugins() {
  return useQuery({
    queryKey: ['plugins'],
    queryFn: pluginService.list,
  });
}

export function useInstallPlugin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => pluginService.install(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plugins'] }),
  });
}

export function useUpdatePlugin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Plugin> }) =>
      pluginService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plugins'] }),
  });
}

export function useDeletePlugin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => pluginService.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plugins'] }),
  });
}

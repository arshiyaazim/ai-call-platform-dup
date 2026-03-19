import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { taskService } from '@/services/tasks';
import type { Task } from '@/types';

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: taskService.list,
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Omit<Task, 'id' | 'last_run' | 'next_run'>) =>
      taskService.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  });
}

export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Task> }) =>
      taskService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  });
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => taskService.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  });
}

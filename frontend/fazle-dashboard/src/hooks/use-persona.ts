import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { personaService } from '@/services/persona';
import type { Persona } from '@/types';

export function usePersona() {
  return useQuery({
    queryKey: ['persona'],
    queryFn: personaService.get,
  });
}

export function useUpdatePersona() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Persona) => personaService.update(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persona'] }),
  });
}

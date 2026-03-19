import { apiGet, apiPut } from './api';
import type { Persona } from '@/types';

export const personaService = {
  get: () => apiGet<Persona>('/admin/persona'),
  update: (data: Persona) => apiPut<Persona>('/admin/persona', data),
};

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { maintenanceService } from '@/services/maintenance';
import type { TableSchema, RowsResponse } from '@/services/maintenance';

export function useMaintenanceTables() {
  return useQuery({
    queryKey: ['maintenance', 'tables'],
    queryFn: async () => {
      const res = await maintenanceService.listTables();
      return res.tables;
    },
  });
}

export function useTableSchema(tableName: string | null) {
  return useQuery({
    queryKey: ['maintenance', 'schema', tableName],
    queryFn: () => maintenanceService.getSchema(tableName!),
    enabled: !!tableName,
  });
}

export function useTableRows(
  tableName: string | null,
  params?: { search?: string; page?: number; per_page?: number; sort_by?: string; sort_dir?: string }
) {
  return useQuery({
    queryKey: ['maintenance', 'rows', tableName, params],
    queryFn: () => maintenanceService.listRows(tableName!, params),
    enabled: !!tableName,
  });
}

export function useMaintenanceRow(tableName: string | null, rowId: string | null) {
  return useQuery({
    queryKey: ['maintenance', 'row', tableName, rowId],
    queryFn: () => maintenanceService.getRow(tableName!, rowId!),
    enabled: !!tableName && !!rowId,
  });
}

export function useCreateRow(tableName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      maintenanceService.createRow(tableName, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['maintenance', 'rows', tableName] });
    },
  });
}

export function useUpdateRow(tableName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rowId, data }: { rowId: string; data: Record<string, unknown> }) =>
      maintenanceService.updateRow(tableName, rowId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['maintenance', 'rows', tableName] });
    },
  });
}

export function useDeleteRow(tableName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rowId: string) =>
      maintenanceService.deleteRow(tableName, rowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['maintenance', 'rows', tableName] });
    },
  });
}

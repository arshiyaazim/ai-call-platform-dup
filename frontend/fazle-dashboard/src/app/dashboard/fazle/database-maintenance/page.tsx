'use client';

import * as React from 'react';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/tables/data-table';
import { ActionDropdown } from '@/components/action-dropdown';
import { StatusBadge } from '@/components/status-badge';
import { ConfirmDialog } from '@/components/dialogs/confirm-dialog';
import { ModalForm } from '@/components/forms/modal-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import {
  useMaintenanceTables,
  useTableSchema,
  useTableRows,
  useCreateRow,
  useUpdateRow,
  useDeleteRow,
} from '@/hooks/use-maintenance';
import type { TableInfo, TableSchema, ColumnSchema } from '@/services/maintenance';
import {
  Database,
  Plus,
  ChevronLeft,
  ChevronRight,
  Shield,
  Lock,
  Eye,
  Pencil,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ── Group display config ───────────────────────────────────

const GROUP_LABELS: Record<string, string> = {
  admin_config: 'Admin Config',
  contacts: 'Contacts & Leads',
  user_rules: 'User Rules',
  knowledge: 'Knowledge',
  users: 'Users',
  social: 'Social',
};

const ACCESS_ICONS: Record<string, React.ReactNode> = {
  read_write: <Pencil className="h-3 w-3" />,
  limited_write: <Lock className="h-3 w-3" />,
  read_only: <Eye className="h-3 w-3" />,
};

// ── Helpers ────────────────────────────────────────────────

function formatCellValue(value: unknown, col: ColumnSchema): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-muted-foreground">—</span>;
  if (col.masked) return <span className="text-muted-foreground">***</span>;

  if (col.type === 'boolean') {
    return value ? (
      <Badge variant="success">Yes</Badge>
    ) : (
      <Badge variant="secondary">No</Badge>
    );
  }

  if (col.type === 'enum') {
    return <StatusBadge status={String(value)} />;
  }

  if (col.type === 'timestamp') {
    if (!value) return '—';
    return new Date(String(value)).toLocaleString();
  }

  if (col.type === 'json') {
    const str = typeof value === 'string' ? value : JSON.stringify(value);
    return (
      <code className="rounded bg-muted px-2 py-1 text-xs line-clamp-1 max-w-[200px] block">
        {str}
      </code>
    );
  }

  const str = String(value);
  if (str.length > 80) return str.slice(0, 80) + '…';
  return str;
}

// ── Main Page ──────────────────────────────────────────────

export default function DatabaseMaintenancePage() {
  const { data: tables = [], isLoading: tablesLoading } = useMaintenanceTables();

  const [selectedTable, setSelectedTable] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState('');
  const [page, setPage] = React.useState(1);

  const { data: schema } = useTableSchema(selectedTable);
  const { data: rowsData, isLoading: rowsLoading } = useTableRows(selectedTable, {
    search: search || undefined,
    page,
    per_page: 50,
  });

  const createMutation = useCreateRow(selectedTable || '');
  const updateMutation = useUpdateRow(selectedTable || '');
  const deleteMutation = useDeleteRow(selectedTable || '');

  const [formOpen, setFormOpen] = React.useState(false);
  const [editRow, setEditRow] = React.useState<Record<string, unknown> | null>(null);
  const [deleteId, setDeleteId] = React.useState<string | null>(null);
  const [formData, setFormData] = React.useState<Record<string, unknown>>({});

  // Reset state when table changes
  React.useEffect(() => {
    setSearch('');
    setPage(1);
    setFormOpen(false);
    setEditRow(null);
    setDeleteId(null);
  }, [selectedTable]);

  // Group tables
  const grouped = React.useMemo(() => {
    const groups: Record<string, TableInfo[]> = {};
    for (const t of tables) {
      if (!groups[t.group]) groups[t.group] = [];
      groups[t.group].push(t);
    }
    return groups;
  }, [tables]);

  // Build columns from schema
  const columns: ColumnDef<Record<string, unknown>>[] = React.useMemo(() => {
    if (!schema) return [];
    const cols: ColumnDef<Record<string, unknown>>[] = schema.columns
      .filter((c) => !c.masked || c.name === schema.primary_key)
      .slice(0, 7) // Show at most 7 columns in the grid
      .map((col) => ({
        accessorKey: col.name,
        header: col.display_name,
        cell: ({ row }: { row: { original: Record<string, unknown> } }) =>
          formatCellValue(row.original[col.name], col),
      }));

    // Actions column if the table supports any mutations
    if (schema.can_update || schema.can_delete) {
      cols.push({
        id: 'actions',
        cell: ({ row }: { row: { original: Record<string, unknown> } }) => {
          const actions = [];
          if (schema.can_update) {
            actions.push({
              label: 'Edit',
              onClick: () => openEdit(row.original),
            });
          }
          if (schema.can_delete) {
            actions.push({
              label: schema.delete_policy === 'hard_delete' ? 'Delete' : 'Archive',
              onClick: () => setDeleteId(String(row.original[schema.primary_key])),
              variant: 'destructive' as const,
              separator: true,
            });
          }
          return <ActionDropdown actions={actions} />;
        },
      });
    }

    return cols;
  }, [schema]);

  // Form helpers
  const editableColumns = React.useMemo(() => {
    if (!schema) return [];
    return schema.columns.filter(
      (c) => !c.masked && !c.immutable && c.name !== schema.primary_key
    );
  }, [schema]);

  const creatableColumns = React.useMemo(() => {
    if (!schema) return [];
    return schema.columns.filter(
      (c) => !c.masked && c.name !== schema.primary_key && c.name !== 'created_at' && c.name !== 'updated_at'
    );
  }, [schema]);

  const openNew = () => {
    setEditRow(null);
    const defaults: Record<string, unknown> = {};
    for (const col of creatableColumns) {
      defaults[col.name] = col.default ?? '';
    }
    setFormData(defaults);
    setFormOpen(true);
  };

  const openEdit = (row: Record<string, unknown>) => {
    setEditRow(row);
    const data: Record<string, unknown> = {};
    for (const col of editableColumns) {
      data[col.name] = row[col.name] ?? '';
    }
    setFormData(data);
    setFormOpen(true);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!schema) return;

    // Filter out empty strings for non-required fields
    const payload: Record<string, unknown> = {};
    const targetCols = editRow ? editableColumns : creatableColumns;
    for (const col of targetCols) {
      const val = formData[col.name];
      if (val === '' && !col.required) continue;
      if (col.type === 'integer' && val !== '') {
        payload[col.name] = Number(val);
      } else if (col.type === 'boolean') {
        payload[col.name] = val === 'true' || val === true;
      } else if (col.type === 'json' && typeof val === 'string' && val.trim()) {
        try {
          payload[col.name] = JSON.parse(val);
        } catch {
          payload[col.name] = val;
        }
      } else {
        payload[col.name] = val;
      }
    }

    if (editRow) {
      await updateMutation.mutateAsync({
        rowId: String(editRow[schema.primary_key]),
        data: payload,
      });
    } else {
      await createMutation.mutateAsync(payload);
    }
    setFormOpen(false);
  };

  const onDelete = async () => {
    if (deleteId) {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const deleteLabel = schema?.delete_policy === 'hard_delete' ? 'Delete' : 'Archive';

  // ── Render ─────────────────────────────────────────────────

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-0">
      {/* Left sidebar: table menu */}
      <div className="w-64 shrink-0 overflow-y-auto border-r bg-card p-3">
        <div className="mb-4 flex items-center gap-2">
          <Database className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold">Tables</h3>
        </div>

        {tablesLoading ? (
          <div className="flex h-32 items-center justify-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : (
          Object.entries(GROUP_LABELS).map(([groupKey, groupLabel]) => {
            const groupTables = grouped[groupKey];
            if (!groupTables?.length) return null;
            return (
              <div key={groupKey} className="mb-4">
                <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {groupLabel}
                </p>
                {groupTables.map((t) => (
                  <button
                    key={t.table_name}
                    onClick={() => setSelectedTable(t.table_name)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                      selectedTable === t.table_name
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                    title={t.description}
                  >
                    {ACCESS_ICONS[t.access_mode] || <Database className="h-3 w-3" />}
                    <span className="truncate">{t.display_name}</span>
                  </button>
                ))}
              </div>
            );
          })
        )}
      </div>

      {/* Main content area */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedTable ? (
          <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
            <Database className="mb-4 h-12 w-12 opacity-40" />
            <p className="text-lg font-medium">Database Maintenance Console</p>
            <p className="mt-1 text-sm">Select a table from the left panel to get started.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold tracking-tight">
                  {schema?.display_name || selectedTable}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {schema?.description}
                  {schema?.access_mode === 'read_only' && (
                    <Badge variant="secondary" className="ml-2">Read Only</Badge>
                  )}
                  {schema?.access_mode === 'limited_write' && (
                    <Badge variant="warning" className="ml-2">Limited Write</Badge>
                  )}
                </p>
              </div>
            </div>

            {/* Data grid */}
            {rowsLoading ? (
              <div className="flex h-64 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              </div>
            ) : (
              <>
                <DataTable
                  columns={columns}
                  data={rowsData?.rows ?? []}
                  searchKey={schema?.columns.some((c) => c.searchable) ? 'search' : undefined}
                  searchPlaceholder={`Search ${schema?.display_name?.toLowerCase()}...`}
                  toolbar={
                    schema?.can_create ? (
                      <Button onClick={openNew} size="sm">
                        <Plus className="mr-2 h-4 w-4" /> Add New
                      </Button>
                    ) : undefined
                  }
                />

                {/* Pagination */}
                {rowsData && rowsData.pages > 1 && (
                  <div className="flex items-center justify-between px-2">
                    <p className="text-sm text-muted-foreground">
                      {rowsData.total} total rows
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        Page {page} of {rowsData.pages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage((p) => Math.min(rowsData.pages, p + 1))}
                        disabled={page >= rowsData.pages}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Create/Edit Modal */}
      <ModalForm
        open={formOpen}
        onOpenChange={setFormOpen}
        title={editRow ? `Edit ${schema?.display_name}` : `Add ${schema?.display_name}`}
      >
        <form onSubmit={onSubmit} className="space-y-4">
          {(editRow ? editableColumns : creatableColumns).map((col) => (
            <div key={col.name} className="space-y-2">
              <Label htmlFor={col.name}>
                {col.display_name}
                {col.required && <span className="ml-1 text-destructive">*</span>}
              </Label>

              {col.type === 'enum' && col.enum_values ? (
                <Select
                  value={String(formData[col.name] ?? '')}
                  onValueChange={(v) => setFormData((prev) => ({ ...prev, [col.name]: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={`Select ${col.display_name.toLowerCase()}`} />
                  </SelectTrigger>
                  <SelectContent>
                    {col.enum_values.map((ev) => (
                      <SelectItem key={ev} value={ev}>
                        {ev}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : col.type === 'boolean' ? (
                <Select
                  value={String(formData[col.name] ?? 'true')}
                  onValueChange={(v) => setFormData((prev) => ({ ...prev, [col.name]: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
              ) : col.type === 'json' ? (
                <textarea
                  id={col.name}
                  value={
                    typeof formData[col.name] === 'object'
                      ? JSON.stringify(formData[col.name], null, 2)
                      : String(formData[col.name] ?? '')
                  }
                  onChange={(e) => setFormData((prev) => ({ ...prev, [col.name]: e.target.value }))}
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="{}"
                />
              ) : (
                <Input
                  id={col.name}
                  type={col.type === 'integer' ? 'number' : col.type === 'timestamp' ? 'datetime-local' : 'text'}
                  value={String(formData[col.name] ?? '')}
                  onChange={(e) => setFormData((prev) => ({ ...prev, [col.name]: e.target.value }))}
                  maxLength={col.max_length ?? undefined}
                  required={col.required}
                />
              )}
            </div>
          ))}

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title={`${deleteLabel} Record`}
        description={
          schema?.delete_policy === 'hard_delete'
            ? 'This will permanently delete this record. This action cannot be undone.'
            : 'This will archive/deactivate this record. It can be restored by an administrator.'
        }
        onConfirm={onDelete}
        loading={deleteMutation.isPending}
        variant="destructive"
      />
    </div>
  );
}

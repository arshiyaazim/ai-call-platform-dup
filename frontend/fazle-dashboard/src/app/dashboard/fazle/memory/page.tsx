'use client';

import * as React from 'react';
import { ColumnDef } from '@tanstack/react-table';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { DataTable } from '@/components/tables/data-table';
import { ActionDropdown } from '@/components/action-dropdown';
import { StatusBadge } from '@/components/status-badge';
import { ConfirmDialog } from '@/components/dialogs/confirm-dialog';
import { ModalForm } from '@/components/forms/modal-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useMemories, useUpdateMemory, useToggleMemoryLock, useDeleteMemory } from '@/hooks/use-memories';
import type { Memory } from '@/types';
import { Plus, Lock, Unlock } from 'lucide-react';

const memorySchema = z.object({
  content: z.string().min(1, 'Content is required'),
  type: z.string().min(1, 'Type is required'),
  status: z.string().min(1, 'Status is required'),
});

type MemoryFormData = z.infer<typeof memorySchema>;

export default function MemoryPage() {
  const { data: memories = [], isLoading } = useMemories();
  const updateMutation = useUpdateMemory();
  const lockMutation = useToggleMemoryLock();
  const deleteMutation = useDeleteMemory();

  const [editItem, setEditItem] = React.useState<Memory | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [deleteId, setDeleteId] = React.useState<string | null>(null);

  const { register, handleSubmit, reset, setValue, formState: { errors } } = useForm<MemoryFormData>({
    resolver: zodResolver(memorySchema),
  });

  const openEdit = (memory: Memory) => {
    setEditItem(memory);
    reset({ content: memory.content, type: memory.type, status: memory.status });
    setFormOpen(true);
  };

  const openNew = () => {
    setEditItem(null);
    reset({ content: '', type: 'knowledge', status: 'active' });
    setFormOpen(true);
  };

  const onSubmit = async (data: MemoryFormData) => {
    if (editItem) {
      await updateMutation.mutateAsync({ id: editItem.id, data });
    }
    setFormOpen(false);
  };

  const onDelete = async () => {
    if (deleteId) {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const columns: ColumnDef<Memory>[] = [
    { accessorKey: 'id', header: 'ID', cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.id.slice(0, 8)}...</span>
    )},
    { accessorKey: 'content', header: 'Content', cell: ({ row }) => (
      <span className="line-clamp-2 max-w-[300px]">{row.original.content}</span>
    )},
    { accessorKey: 'type', header: 'Type' },
    { accessorKey: 'created', header: 'Created', cell: ({ row }) => (
      new Date(row.original.created).toLocaleDateString()
    )},
    { accessorKey: 'status', header: 'Status', cell: ({ row }) => (
      <StatusBadge status={row.original.status} />
    )},
    { accessorKey: 'locked', header: 'Lock', cell: ({ row }) => (
      <button
        onClick={() => lockMutation.mutate(row.original.id)}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        disabled={lockMutation.isPending}
      >
        {row.original.locked ? (
          <><Lock className="h-4 w-4 text-yellow-500" /> Locked</>
        ) : (
          <><Unlock className="h-4 w-4" /> Unlocked</>
        )}
      </button>
    )},
    { id: 'actions', cell: ({ row }) => (
      <ActionDropdown
        actions={[
          { label: 'Edit', onClick: () => openEdit(row.original) },
          { label: 'Delete', onClick: () => setDeleteId(row.original.id), variant: 'destructive', separator: true },
        ]}
      />
    )},
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Memory Manager</h2>
          <p className="text-muted-foreground">Manage Fazle AI memory entries.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={memories}
          searchKey="content"
          searchPlaceholder="Search memories..."
          toolbar={
            <Button onClick={openNew} size="sm">
              <Plus className="mr-2 h-4 w-4" /> Add New
            </Button>
          }
        />
      )}

      {/* Edit / Add Modal */}
      <ModalForm
        open={formOpen}
        onOpenChange={setFormOpen}
        title={editItem ? 'Edit Memory' : 'Add Memory'}
      >
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="content">Content</Label>
            <Textarea id="content" rows={4} {...register('content')} />
            {errors.content && <p className="text-sm text-destructive">{errors.content.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="type">Type</Label>
            <Select
              defaultValue={editItem?.type || 'knowledge'}
              onValueChange={(v) => setValue('type', v)}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="knowledge">Knowledge</SelectItem>
                <SelectItem value="conversation">Conversation</SelectItem>
                <SelectItem value="preference">Preference</SelectItem>
                <SelectItem value="fact">Fact</SelectItem>
              </SelectContent>
            </Select>
            {errors.type && <p className="text-sm text-destructive">{errors.type.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="status">Status</Label>
            <Select
              defaultValue={editItem?.status || 'active'}
              onValueChange={(v) => setValue('status', v)}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Memory"
        description="Are you sure you want to delete this memory entry? This action cannot be undone."
        onConfirm={onDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  );
}

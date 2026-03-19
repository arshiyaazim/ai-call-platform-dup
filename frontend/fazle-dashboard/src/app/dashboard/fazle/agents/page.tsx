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
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAgents, useCreateAgent, useUpdateAgent, useDeleteAgent } from '@/hooks/use-agents';
import type { Agent } from '@/types';
import { Plus } from 'lucide-react';

const agentSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  model: z.string().min(1, 'Model is required'),
  priority: z.coerce.number().int().min(0).max(100),
  status: z.enum(['active', 'inactive', 'error']),
  enabled: z.boolean(),
});

type AgentFormData = z.infer<typeof agentSchema>;

export default function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents();
  const createMutation = useCreateAgent();
  const updateMutation = useUpdateAgent();
  const deleteMutation = useDeleteAgent();

  const [editItem, setEditItem] = React.useState<Agent | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [deleteId, setDeleteId] = React.useState<string | null>(null);

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<AgentFormData>({
    resolver: zodResolver(agentSchema),
  });

  const openEdit = (agent: Agent) => {
    setEditItem(agent);
    reset({ name: agent.name, model: agent.model, priority: agent.priority, status: agent.status, enabled: agent.enabled });
    setFormOpen(true);
  };

  const openNew = () => {
    setEditItem(null);
    reset({ name: '', model: 'gpt-4o', priority: 50, status: 'active', enabled: true });
    setFormOpen(true);
  };

  const onSubmit = async (data: AgentFormData) => {
    if (editItem) {
      await updateMutation.mutateAsync({ id: editItem.id, data });
    } else {
      await createMutation.mutateAsync(data);
    }
    setFormOpen(false);
  };

  const toggleEnabled = async (agent: Agent) => {
    await updateMutation.mutateAsync({
      id: agent.id,
      data: { enabled: !agent.enabled, status: agent.enabled ? 'inactive' : 'active' },
    });
  };

  const onDelete = async () => {
    if (deleteId) {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const columns: ColumnDef<Agent>[] = [
    { accessorKey: 'name', header: 'Agent Name' },
    { accessorKey: 'model', header: 'Model' },
    { accessorKey: 'priority', header: 'Priority' },
    { accessorKey: 'status', header: 'Status', cell: ({ row }) => (
      <StatusBadge status={row.original.status} />
    )},
    { id: 'enabled', header: 'Enabled', cell: ({ row }) => (
      <Switch
        checked={row.original.enabled}
        onCheckedChange={() => toggleEnabled(row.original)}
        disabled={updateMutation.isPending}
      />
    )},
    { id: 'actions', cell: ({ row }) => (
      <ActionDropdown
        actions={[
          { label: 'Edit', onClick: () => openEdit(row.original) },
          { label: row.original.enabled ? 'Disable' : 'Enable', onClick: () => toggleEnabled(row.original) },
          { label: 'Delete', onClick: () => setDeleteId(row.original.id), variant: 'destructive', separator: true },
        ]}
      />
    )},
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Agent Manager</h2>
          <p className="text-muted-foreground">Manage AI agents and their configurations.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={agents}
          searchKey="name"
          searchPlaceholder="Search agents..."
          toolbar={
            <Button onClick={openNew} size="sm">
              <Plus className="mr-2 h-4 w-4" /> Add New
            </Button>
          }
        />
      )}

      <ModalForm
        open={formOpen}
        onOpenChange={setFormOpen}
        title={editItem ? 'Edit Agent' : 'Add Agent'}
      >
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Agent Name</Label>
            <Input id="name" {...register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="model">Model</Label>
            <Select
              defaultValue={editItem?.model || 'gpt-4o'}
              onValueChange={(v) => setValue('model', v)}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                <SelectItem value="gpt-4-turbo">GPT-4 Turbo</SelectItem>
                <SelectItem value="claude-3-opus">Claude 3 Opus</SelectItem>
                <SelectItem value="claude-3-sonnet">Claude 3 Sonnet</SelectItem>
                <SelectItem value="qwen2.5:3b">Qwen 2.5 3B</SelectItem>
                <SelectItem value="ollama-local">Ollama Local</SelectItem>
              </SelectContent>
            </Select>
            {errors.model && <p className="text-sm text-destructive">{errors.model.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="priority">Priority (0-100)</Label>
            <Input id="priority" type="number" min={0} max={100} {...register('priority')} />
            {errors.priority && <p className="text-sm text-destructive">{errors.priority.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="status">Status</Label>
            <Select
              defaultValue={editItem?.status || 'active'}
              onValueChange={(v) => setValue('status', v as Agent['status'])}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              id="enabled"
              checked={watch('enabled')}
              onCheckedChange={(checked) => setValue('enabled', checked)}
            />
            <Label htmlFor="enabled">Enabled</Label>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
              {(createMutation.isPending || updateMutation.isPending) ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </ModalForm>

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Agent"
        description="Are you sure you want to delete this agent? This action cannot be undone."
        onConfirm={onDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  );
}

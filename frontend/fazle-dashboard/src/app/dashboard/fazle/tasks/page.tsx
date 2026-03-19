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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useTasks, useCreateTask, useUpdateTask, useDeleteTask } from '@/hooks/use-tasks';
import type { Task } from '@/types';
import { Plus } from 'lucide-react';

const cronPresets = [
  { label: 'Every minute', value: '* * * * *' },
  { label: 'Every 5 minutes', value: '*/5 * * * *' },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every day at midnight', value: '0 0 * * *' },
  { label: 'Every Monday', value: '0 0 * * 1' },
  { label: 'Custom', value: 'custom' },
];

const taskSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  schedule: z.string().min(1, 'Schedule is required'),
  status: z.enum(['running', 'paused', 'completed', 'failed']),
});

type TaskFormData = z.infer<typeof taskSchema>;

export default function TasksPage() {
  const { data: tasks = [], isLoading } = useTasks();
  const createMutation = useCreateTask();
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask();

  const [editItem, setEditItem] = React.useState<Task | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [deleteId, setDeleteId] = React.useState<string | null>(null);
  const [cronPreset, setCronPreset] = React.useState('custom');

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<TaskFormData>({
    resolver: zodResolver(taskSchema),
  });

  const openEdit = (task: Task) => {
    setEditItem(task);
    reset({ name: task.name, schedule: task.schedule, status: task.status });
    const preset = cronPresets.find((p) => p.value === task.schedule);
    setCronPreset(preset ? preset.value : 'custom');
    setFormOpen(true);
  };

  const openNew = () => {
    setEditItem(null);
    reset({ name: '', schedule: '0 * * * *', status: 'running' });
    setCronPreset('0 * * * *');
    setFormOpen(true);
  };

  const onSubmit = async (data: TaskFormData) => {
    if (editItem) {
      await updateMutation.mutateAsync({ id: editItem.id, data });
    } else {
      await createMutation.mutateAsync(data);
    }
    setFormOpen(false);
  };

  const togglePause = async (task: Task) => {
    await updateMutation.mutateAsync({
      id: task.id,
      data: { status: task.status === 'paused' ? 'running' : 'paused' },
    });
  };

  const onDelete = async () => {
    if (deleteId) {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const formatDate = (date: string | null) => {
    if (!date) return '—';
    return new Date(date).toLocaleString();
  };

  const columns: ColumnDef<Task>[] = [
    { accessorKey: 'name', header: 'Task Name' },
    { accessorKey: 'schedule', header: 'Schedule', cell: ({ row }) => (
      <code className="rounded bg-muted px-2 py-1 text-xs">{row.original.schedule}</code>
    )},
    { accessorKey: 'status', header: 'Status', cell: ({ row }) => (
      <StatusBadge status={row.original.status} />
    )},
    { accessorKey: 'last_run', header: 'Last Run', cell: ({ row }) => formatDate(row.original.last_run) },
    { accessorKey: 'next_run', header: 'Next Run', cell: ({ row }) => formatDate(row.original.next_run) },
    { id: 'actions', cell: ({ row }) => (
      <ActionDropdown
        actions={[
          { label: 'Edit', onClick: () => openEdit(row.original) },
          {
            label: row.original.status === 'paused' ? 'Resume' : 'Pause',
            onClick: () => togglePause(row.original),
          },
          { label: 'Delete', onClick: () => setDeleteId(row.original.id), variant: 'destructive', separator: true },
        ]}
      />
    )},
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Task Scheduler</h2>
          <p className="text-muted-foreground">Manage scheduled tasks and cron jobs.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={tasks}
          searchKey="name"
          searchPlaceholder="Search tasks..."
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
        title={editItem ? 'Edit Task' : 'Add Task'}
      >
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Task Name</Label>
            <Input id="name" {...register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <Label>Schedule Preset</Label>
            <Select
              value={cronPreset}
              onValueChange={(v) => {
                setCronPreset(v);
                if (v !== 'custom') setValue('schedule', v);
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {cronPresets.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="schedule">Cron Expression</Label>
            <Input
              id="schedule"
              {...register('schedule')}
              placeholder="* * * * *"
              className="font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Format: minute hour day month weekday
            </p>
            {errors.schedule && <p className="text-sm text-destructive">{errors.schedule.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="status">Status</Label>
            <Select
              defaultValue={editItem?.status || 'running'}
              onValueChange={(v) => setValue('status', v as Task['status'])}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="running">Running</SelectItem>
                <SelectItem value="paused">Paused</SelectItem>
              </SelectContent>
            </Select>
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
        title="Delete Task"
        description="Are you sure you want to delete this task? This action cannot be undone."
        onConfirm={onDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  );
}

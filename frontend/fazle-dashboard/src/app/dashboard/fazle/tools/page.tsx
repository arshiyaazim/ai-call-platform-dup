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
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { usePlugins, useInstallPlugin, useUpdatePlugin, useDeletePlugin } from '@/hooks/use-plugins';
import type { Plugin } from '@/types';
import { Plus, Upload } from 'lucide-react';

const pluginSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().min(1, 'Description is required'),
  version: z.string().min(1, 'Version is required'),
  status: z.enum(['active', 'inactive', 'error']),
  enabled: z.boolean(),
});

type PluginFormData = z.infer<typeof pluginSchema>;

export default function ToolsPage() {
  const { data: plugins = [], isLoading } = usePlugins();
  const installMutation = useInstallPlugin();
  const updateMutation = useUpdatePlugin();
  const deleteMutation = useDeletePlugin();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const [editItem, setEditItem] = React.useState<Plugin | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [deleteId, setDeleteId] = React.useState<string | null>(null);

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<PluginFormData>({
    resolver: zodResolver(pluginSchema),
  });

  const openEdit = (plugin: Plugin) => {
    setEditItem(plugin);
    reset({
      name: plugin.name,
      description: plugin.description,
      version: plugin.version,
      status: plugin.status,
      enabled: plugin.enabled,
    });
    setFormOpen(true);
  };

  const openNew = () => {
    setEditItem(null);
    reset({ name: '', description: '', version: '1.0.0', status: 'active', enabled: true });
    setFormOpen(true);
  };

  const onSubmit = async (data: PluginFormData) => {
    if (editItem) {
      await updateMutation.mutateAsync({ id: editItem.id, data });
    }
    setFormOpen(false);
  };

  const toggleEnabled = async (plugin: Plugin) => {
    await updateMutation.mutateAsync({
      id: plugin.id,
      data: { enabled: !plugin.enabled, status: plugin.enabled ? 'inactive' : 'active' },
    });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await installMutation.mutateAsync(file);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const onDelete = async () => {
    if (deleteId) {
      await deleteMutation.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const columns: ColumnDef<Plugin>[] = [
    { accessorKey: 'name', header: 'Tool Name' },
    { accessorKey: 'description', header: 'Description', cell: ({ row }) => (
      <span className="line-clamp-2 max-w-[300px]">{row.original.description}</span>
    )},
    { accessorKey: 'version', header: 'Version' },
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
          <h2 className="text-3xl font-bold tracking-tight">Plugin Manager</h2>
          <p className="text-muted-foreground">Manage tools and plugins for Fazle AI.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={plugins}
          searchKey="name"
          searchPlaceholder="Search plugins..."
          toolbar={
            <div className="flex items-center gap-2">
              <Button onClick={openNew} size="sm">
                <Plus className="mr-2 h-4 w-4" /> Add New
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={installMutation.isPending}
              >
                <Upload className="mr-2 h-4 w-4" />
                {installMutation.isPending ? 'Installing...' : 'Install Manifest'}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
          }
        />
      )}

      <ModalForm
        open={formOpen}
        onOpenChange={setFormOpen}
        title={editItem ? 'Edit Plugin' : 'Add Plugin'}
      >
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Tool Name</Label>
            <Input id="name" {...register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" rows={3} {...register('description')} />
            {errors.description && <p className="text-sm text-destructive">{errors.description.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="version">Version</Label>
            <Input id="version" {...register('version')} placeholder="1.0.0" />
            {errors.version && <p className="text-sm text-destructive">{errors.version.message}</p>}
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
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </ModalForm>

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Plugin"
        description="Are you sure you want to delete this plugin? This action cannot be undone."
        onConfirm={onDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  );
}

'use client';

import { Badge } from '@/components/ui/badge';

interface StatusBadgeProps {
  status: string;
}

const statusMap: Record<string, { label: string; variant: 'success' | 'destructive' | 'warning' | 'secondary' }> = {
  active: { label: 'Active', variant: 'success' },
  inactive: { label: 'Inactive', variant: 'secondary' },
  running: { label: 'Running', variant: 'success' },
  paused: { label: 'Paused', variant: 'warning' },
  completed: { label: 'Completed', variant: 'secondary' },
  failed: { label: 'Failed', variant: 'destructive' },
  error: { label: 'Error', variant: 'destructive' },
  locked: { label: 'Locked', variant: 'warning' },
  unlocked: { label: 'Unlocked', variant: 'success' },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusMap[status.toLowerCase()] ?? { label: status, variant: 'secondary' as const };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

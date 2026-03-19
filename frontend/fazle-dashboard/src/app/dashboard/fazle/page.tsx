'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDashboardStats } from '@/hooks/use-dashboard';
import { Bot, Brain, CalendarClock, Zap, MessageSquare } from 'lucide-react';

const statCards = [
  { key: 'active_agents' as const, label: 'Active Agents', icon: Bot, color: 'text-blue-500' },
  { key: 'total_memories' as const, label: 'Total Memories', icon: Brain, color: 'text-purple-500' },
  { key: 'scheduled_tasks' as const, label: 'Scheduled Tasks', icon: CalendarClock, color: 'text-orange-500' },
  { key: 'average_latency' as const, label: 'Avg Latency (ms)', icon: Zap, color: 'text-green-500' },
  { key: 'active_conversations' as const, label: 'Active Conversations', icon: MessageSquare, color: 'text-cyan-500' },
];

export default function FazleDashboardPage() {
  const { data: stats, isLoading, error } = useDashboardStats();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Overview</h2>
        <p className="text-muted-foreground">Fazle AI platform statistics at a glance.</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load dashboard stats. Please try again.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {statCards.map((card) => (
          <Card key={card.key}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.label}
              </CardTitle>
              <card.icon className={`h-5 w-5 ${card.color}`} />
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="h-8 w-20 animate-pulse rounded bg-muted" />
              ) : (
                <p className="text-3xl font-bold">
                  {stats?.[card.key] != null
                    ? card.key === 'average_latency'
                      ? `${Math.round(stats[card.key])}ms`
                      : stats[card.key].toLocaleString()
                    : '—'}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

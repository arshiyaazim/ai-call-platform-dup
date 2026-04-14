'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { opsService, type OpsAlert } from '@/services/ops';
import {
  Bell, Loader2, RefreshCw, AlertTriangle, AlertCircle, Info,
  Ship, Banknote, Clock,
} from 'lucide-react';

type TabKey = 'all' | 'pending_duty' | 'duplicate_payment' | 'missing_payment' | 'abnormal_payment';

const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: 'all', label: 'All Alerts', icon: <Bell className="w-4 h-4" /> },
  { key: 'pending_duty', label: 'Pending Duties', icon: <Clock className="w-4 h-4" /> },
  { key: 'duplicate_payment', label: 'Duplicates', icon: <AlertTriangle className="w-4 h-4" /> },
  { key: 'missing_payment', label: 'Missing Payments', icon: <Ship className="w-4 h-4" /> },
  { key: 'abnormal_payment', label: 'Abnormal', icon: <Banknote className="w-4 h-4" /> },
];

const severityConfig = {
  high: { color: 'destructive' as const, icon: <AlertTriangle className="w-4 h-4" /> },
  medium: { color: 'default' as const, icon: <AlertCircle className="w-4 h-4" /> },
  low: { color: 'secondary' as const, icon: <Info className="w-4 h-4" /> },
};

export default function AlertsPage() {
  const [loading, setLoading] = React.useState(true);
  const [alerts, setAlerts] = React.useState<OpsAlert[]>([]);
  const [summary, setSummary] = React.useState({ high: 0, medium: 0, low: 0 });
  const [activeTab, setActiveTab] = React.useState<TabKey>('all');
  const [days, setDays] = React.useState('7');
  const [error, setError] = React.useState('');

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await opsService.getAllAlerts(parseInt(days) || 7);
      setAlerts(data.alerts);
      setSummary(data.summary);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, [days]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh every 60s
  React.useEffect(() => {
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const filtered = activeTab === 'all'
    ? alerts
    : alerts.filter(a => a.type === activeTab);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          <Bell className="inline w-6 h-6 mr-2" />
          Smart Alerts
        </h1>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <label className="text-xs text-muted-foreground">Duty threshold (days)</label>
            <Input
              type="number"
              value={days}
              onChange={e => setDays(e.target.value)}
              className="w-16 h-8 text-sm"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Alerts</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{alerts.length}</p></CardContent>
        </Card>
        <Card className="border-red-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-red-500">
              <AlertTriangle className="inline w-4 h-4 mr-1" /> High
            </CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold text-red-500">{summary.high}</p></CardContent>
        </Card>
        <Card className="border-yellow-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-yellow-600">
              <AlertCircle className="inline w-4 h-4 mr-1" /> Medium
            </CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold text-yellow-600">{summary.medium}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Info className="inline w-4 h-4 mr-1" /> Low
            </CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{summary.low}</p></CardContent>
        </Card>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b">
        {tabs.map(tab => {
          const count = tab.key === 'all'
            ? alerts.length
            : alerts.filter(a => a.type === tab.key).length;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1 px-3 py-2 text-sm border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-primary font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.icon} {tab.label}
              {count > 0 && (
                <Badge variant="secondary" className="ml-1 text-xs">{count}</Badge>
              )}
            </button>
          );
        })}
      </div>

      {/* Alert list */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No alerts in this category
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {filtered.map((alert, i) => {
            const sev = severityConfig[alert.severity];
            return (
              <Card key={i} className={alert.severity === 'high' ? 'border-red-200' : ''}>
                <CardContent className="flex items-start gap-3 py-3">
                  <div className="mt-0.5">{sev.icon}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{alert.title}</span>
                      <Badge variant={sev.color} className="text-xs">{alert.severity}</Badge>
                      <Badge variant="outline" className="text-xs">{alert.type.replace(/_/g, ' ')}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">{alert.description}</p>
                    {alert.entity_id && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {alert.entity_type} #{alert.entity_id}
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

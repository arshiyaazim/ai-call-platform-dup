'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { gdprService, type GdprRequest, type GdprStats } from '@/services/gdpr';
import {
  ShieldCheck, Loader2, RefreshCw, RotateCcw, Trash2, Download,
  ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2, Clock,
  XCircle, Activity, FileText,
} from 'lucide-react';

const PAGE_SIZE = 50;

function statusColor(status: string) {
  switch (status) {
    case 'completed': return 'bg-green-500/10 text-green-700 border-green-300';
    case 'processing': return 'bg-blue-500/10 text-blue-700 border-blue-300';
    case 'failed': return 'bg-red-500/10 text-red-700 border-red-300';
    case 'pending': return 'bg-yellow-500/10 text-yellow-700 border-yellow-300';
    default: return 'bg-gray-500/10 text-gray-700 border-gray-300';
  }
}

export default function GdprAdminPage() {
  const [stats, setStats] = React.useState<GdprStats | null>(null);
  const [requests, setRequests] = React.useState<GdprRequest[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState<string>('');
  const [loading, setLoading] = React.useState(true);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const showMsg = (text: string, type: 'success' | 'error') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  const fetchData = React.useCallback(async () => {
    try {
      const [statsRes, reqRes] = await Promise.all([
        gdprService.adminGetStats(),
        gdprService.adminGetRequests(PAGE_SIZE, page * PAGE_SIZE, statusFilter || undefined),
      ]);
      setStats(statsRes);
      setRequests(reqRes.requests || []);
      setTotal(reqRes.total || 0);
    } catch {
      showMsg('Failed to load GDPR data', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  const handleRetryFailed = async () => {
    setActionLoading('retry');
    try {
      await gdprService.adminRetryFailed();
      showMsg('Failed requests queued for retry', 'success');
      fetchData();
    } catch {
      showMsg('Retry failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleProcessDeletions = async () => {
    setActionLoading('deletions');
    try {
      await gdprService.adminProcessDeletions();
      showMsg('Permanent deletion sweep queued', 'success');
      fetchData();
    } catch {
      showMsg('Failed to process deletions', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCleanupExports = async () => {
    setActionLoading('cleanup');
    try {
      const res = await gdprService.adminCleanupExports();
      showMsg(`Cleaned ${res.cleaned} expired exports, ${res.remaining} remaining`, 'success');
      fetchData();
    } catch {
      showMsg('Cleanup failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">GDPR Administration</h1>
            <p className="text-sm text-muted-foreground">Monitor compliance requests, manage deletions and exports</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); fetchData(); }}>
          <RefreshCw className="mr-2 h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Feedback */}
      {message && (
        <div className={`rounded-lg border p-3 text-sm ${message.type === 'success' ? 'border-green-300 bg-green-50 text-green-800' : 'border-red-300 bg-red-50 text-red-800'}`}>
          {message.type === 'success' ? <CheckCircle2 className="mr-2 inline h-4 w-4" /> : <XCircle className="mr-2 inline h-4 w-4" />}
          {message.text}
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Total Requests</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_requests}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Completed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                <span className="text-2xl font-bold">{stats.completed}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Failed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <XCircle className="h-5 w-5 text-red-500" />
                <span className="text-2xl font-bold">{stats.failed}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Pending</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <Clock className="h-5 w-5 text-yellow-500" />
                <span className="text-2xl font-bold">{stats.pending}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Breakdown + Actions */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between"><span>Deletions</span><span className="font-mono">{stats.total_deletions}</span></div>
              <div className="flex justify-between"><span>Exports</span><span className="font-mono">{stats.total_exports}</span></div>
              <div className="flex justify-between"><span>Facebook Callbacks</span><span className="font-mono">{stats.total_fb_deletions}</span></div>
              <div className="flex justify-between"><span>Pending Permanent Deletions</span><span className="font-mono">{stats.pending_permanent_deletions}</span></div>
              <div className="flex justify-between"><span>Active Exports in Store</span><span className="font-mono">{stats.export_store_size}</span></div>
              <div className="flex justify-between">
                <span>Avg Completion Time</span>
                <span className="font-mono">{stats.avg_completion_secs ? `${stats.avg_completion_secs.toFixed(1)}s` : 'N/A'}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Admin Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={handleRetryFailed}
                disabled={!!actionLoading}
              >
                {actionLoading === 'retry' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
                Retry Failed Requests
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={handleProcessDeletions}
                disabled={!!actionLoading}
              >
                {actionLoading === 'deletions' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                Process Expired Deletions
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={handleCleanupExports}
                disabled={!!actionLoading}
              >
                {actionLoading === 'cleanup' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
                Cleanup Expired Exports
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Requests Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" /> GDPR Requests
            </CardTitle>
            <div className="flex items-center gap-2">
              <select
                className="rounded-md border bg-background px-3 py-1.5 text-sm"
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
              >
                <option value="">All Status</option>
                <option value="processing">Processing</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="pending">Pending</option>
              </select>
              <span className="text-sm text-muted-foreground">{total} total</span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Created</th>
                  <th className="pb-2 pr-4">Completed</th>
                  <th className="pb-2 pr-4">Retries</th>
                  <th className="pb-2">Error</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req) => (
                  <tr key={req.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">
                      <Badge variant="outline" className="text-xs">
                        {req.request_type}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4">
                      <Badge variant="outline" className={statusColor(req.status)}>
                        {req.status}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs">
                      {new Date(req.created_at).toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs">
                      {req.completed_at ? new Date(req.completed_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-2 pr-4 text-center">{req.retry_count ?? 0}</td>
                    <td className="max-w-[200px] truncate py-2 text-xs text-muted-foreground">
                      {req.error_message || '—'}
                    </td>
                  </tr>
                ))}
                {requests.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted-foreground">
                      No GDPR requests found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

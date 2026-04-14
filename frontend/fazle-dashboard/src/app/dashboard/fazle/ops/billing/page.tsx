'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { opsService, type VesselBilling } from '@/services/ops';
import {
  Ship, Loader2, RefreshCw, Download, DollarSign,
} from 'lucide-react';

export default function BillingPage() {
  const [loading, setLoading] = React.useState(true);
  const [vessels, setVessels] = React.useState<VesselBilling[]>([]);
  const [from, setFrom] = React.useState('');
  const [to, setTo] = React.useState('');
  const [error, setError] = React.useState('');

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      const data = await opsService.getBillingVesselSummary(params);
      setVessels(data.vessels);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load billing');
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  const grandTotal = vessels.reduce((s, v) => s + parseInt(v.total_cost || '0'), 0);
  const totalTrips = vessels.reduce((s, v) => s + parseInt(v.total_trips || '0'), 0);

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      const blob = await opsService.exportPrograms(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `programs_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          <DollarSign className="inline w-6 h-6 mr-2" />
          Vessel Billing
        </h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="w-4 h-4 mr-1" /> Export CSV
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Date filters */}
      <div className="flex gap-4 items-end">
        <div>
          <label className="text-xs text-muted-foreground">From</label>
          <Input type="date" value={from} onChange={e => setFrom(e.target.value)} className="w-40" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">To</label>
          <Input type="date" value={to} onChange={e => setTo(e.target.value)} className="w-40" />
        </div>
        <Button size="sm" onClick={fetchData}>Filter</Button>
        {(from || to) && (
          <Button variant="ghost" size="sm" onClick={() => { setFrom(''); setTo(''); }}>Clear</Button>
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Totals bar */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Vessels</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{vessels.length}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Trips</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{totalTrips}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Grand Total Cost</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">৳{grandTotal.toLocaleString()}</p></CardContent>
        </Card>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>
              <Ship className="inline w-5 h-5 mr-1" /> Billing by Mother Vessel
            </CardTitle>
          </CardHeader>
          <CardContent>
            {vessels.length === 0 ? (
              <p className="text-sm text-muted-foreground">No billing data found</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-2">Mother Vessel</th>
                      <th className="p-2 text-right">Trips</th>
                      <th className="p-2 text-right">Escorts</th>
                      <th className="p-2 text-right">Food</th>
                      <th className="p-2 text-right">Transport</th>
                      <th className="p-2 text-right">Total Cost</th>
                      <th className="p-2 text-center">Status</th>
                      <th className="p-2">Period</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vessels.map((v, i) => (
                      <tr key={i} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">{v.mother_vessel}</td>
                        <td className="p-2 text-right">{v.total_trips}</td>
                        <td className="p-2 text-right">{v.total_escorts}</td>
                        <td className="p-2 text-right">৳{parseInt(v.total_food || '0').toLocaleString()}</td>
                        <td className="p-2 text-right">৳{parseInt(v.total_transport || '0').toLocaleString()}</td>
                        <td className="p-2 text-right font-bold">৳{parseInt(v.total_cost || '0').toLocaleString()}</td>
                        <td className="p-2 text-center">
                          {parseInt(v.running_count || '0') > 0 && (
                            <Badge variant="outline" className="mr-1">{v.running_count} running</Badge>
                          )}
                          {parseInt(v.completed_count || '0') > 0 && (
                            <Badge variant="secondary">{v.completed_count} done</Badge>
                          )}
                        </td>
                        <td className="p-2 text-xs text-muted-foreground">
                          {v.first_trip?.slice?.(0, 10) || ''} – {v.last_trip?.slice?.(0, 10) || ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

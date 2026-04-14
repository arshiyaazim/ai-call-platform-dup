'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { opsService, type OpsProgram, type OpsPayment } from '@/services/ops';
import {
  Ship, Banknote, Users, CalendarCheck, Loader2, RefreshCw,
  ArrowRight,
} from 'lucide-react';
import Link from 'next/link';

export default function OpsDashboardPage() {
  const [loading, setLoading] = React.useState(true);
  const [programs, setPrograms] = React.useState<OpsProgram[]>([]);
  const [payments, setPayments] = React.useState<OpsPayment[]>([]);
  const [paymentSummary, setPaymentSummary] = React.useState<{
    running_total: string; completed_total: string;
    running_count: string; completed_count: string;
  } | null>(null);
  const [employeeCount, setEmployeeCount] = React.useState(0);
  const [error, setError] = React.useState('');

  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    try {
      const [progs, pays, paySummary, emps] = await Promise.all([
        opsService.listPrograms({ status: 'running' }),
        opsService.listPayments({ status: 'running' }),
        opsService.paymentSummary(),
        opsService.listEmployees(),
      ]);
      setPrograms(progs);
      setPayments(pays);
      setPaymentSummary(paySummary);
      setEmployeeCount(emps.length);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Ops Dashboard</h1>
        <Button variant="outline" size="sm" onClick={fetchAll}>
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Ship className="inline w-4 h-4 mr-1" /> Running Programs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{programs.length}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Banknote className="inline w-4 h-4 mr-1" /> Running Payments
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">৳{paymentSummary?.running_total || '0'}</p>
            <p className="text-xs text-muted-foreground">{paymentSummary?.running_count || '0'} entries</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Users className="inline w-4 h-4 mr-1" /> Employees
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{employeeCount}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Banknote className="inline w-4 h-4 mr-1" /> Completed Payments
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">৳{paymentSummary?.completed_total || '0'}</p>
            <p className="text-xs text-muted-foreground">{paymentSummary?.completed_count || '0'} entries</p>
          </CardContent>
        </Card>
      </div>

      {/* Running Programs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Running Programs</CardTitle>
            <Link href="/dashboard/fazle/ops/search">
              <Button variant="ghost" size="sm">View All <ArrowRight className="w-4 h-4 ml-1" /></Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {programs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No running programs</p>
          ) : (
            <div className="space-y-2">
              {programs.slice(0, 10).map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2 border rounded-md text-sm">
                  <div>
                    <span className="font-medium">{p.mother_vessel}</span>
                    {p.lighter_vessel && <span className="text-muted-foreground ml-2">→ {p.lighter_vessel}</span>}
                    {p.destination && <span className="text-muted-foreground ml-2">@ {p.destination}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{p.date?.slice(0, 10)}</span>
                    <Badge variant="outline">{p.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Running Payments */}
      <Card>
        <CardHeader>
          <CardTitle>Running Payments</CardTitle>
        </CardHeader>
        <CardContent>
          {payments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No running payments</p>
          ) : (
            <div className="space-y-2">
              {payments.slice(0, 10).map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2 border rounded-md text-sm">
                  <div>
                    <span className="font-medium">{p.name}</span>
                    <span className="text-muted-foreground ml-2">({p.employee_id})</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">৳{p.amount}</span>
                    <Badge variant={p.method === 'B' ? 'default' : 'secondary'}>
                      {p.method === 'B' ? 'bKash' : 'Nagad'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

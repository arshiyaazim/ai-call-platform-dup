'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { opsService, type EmployeeSalary, type OpsRate } from '@/services/ops';
import {
  Wallet, Loader2, RefreshCw, Download, Users, Settings,
} from 'lucide-react';

export default function SalaryPage() {
  const [loading, setLoading] = React.useState(true);
  const [employees, setEmployees] = React.useState<EmployeeSalary[]>([]);
  const [rates, setRates] = React.useState<OpsRate[]>([]);
  const [dailyRate, setDailyRate] = React.useState(150);
  const [from, setFrom] = React.useState('');
  const [to, setTo] = React.useState('');
  const [error, setError] = React.useState('');
  const [showRates, setShowRates] = React.useState(false);

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      const [salaryData, rateData] = await Promise.all([
        opsService.getSalarySummary(params),
        opsService.getRates(),
      ]);
      setEmployees(salaryData.employees);
      setDailyRate(salaryData.daily_rate);
      setRates(rateData.rates);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load salary data');
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  React.useEffect(() => { fetchData(); }, [fetchData]);

  const totalDutyDays = employees.reduce((s, e) => s + e.duty_days, 0);
  const totalSalary = employees.reduce((s, e) => s + e.calculated_salary, 0);
  const totalDue = employees.reduce((s, e) => s + e.net_due, 0);

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      const blob = await opsService.exportSalary(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `salary_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  const handleRateUpdate = async (id: number, amount: number) => {
    try {
      await opsService.updateRate(id, { amount });
      fetchData();
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          <Wallet className="inline w-6 h-6 mr-2" />
          Employee Salary
        </h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowRates(!showRates)}>
            <Settings className="w-4 h-4 mr-1" /> Rates
          </Button>
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

      {/* Rate configuration panel */}
      {showRates && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Rate Configuration (Daily Rate: ৳{dailyRate})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-3">
              {rates.map(r => (
                <div key={r.id} className="flex items-center gap-2 p-2 border rounded">
                  <span className="text-sm font-medium">
                    {r.rate_type === 'daily' ? 'Daily' : r.destination}
                  </span>
                  <Input
                    type="number"
                    defaultValue={r.amount}
                    className="w-24 h-8 text-sm"
                    onBlur={e => {
                      const val = parseInt(e.target.value);
                      if (val && val !== r.amount) handleRateUpdate(r.id, val);
                    }}
                  />
                  <span className="text-xs text-muted-foreground">৳</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Totals bar */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              <Users className="inline w-4 h-4 mr-1" /> Employees
            </CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{employees.length}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Duty Days</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">{totalDutyDays}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Calculated Salary</CardTitle>
          </CardHeader>
          <CardContent><p className="text-3xl font-bold">৳{totalSalary.toLocaleString()}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Net Due</CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-3xl font-bold ${totalDue > 0 ? 'text-red-500' : 'text-green-500'}`}>
              ৳{totalDue.toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Employee Salary Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            {employees.length === 0 ? (
              <p className="text-sm text-muted-foreground">No salary data found</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-2">Employee</th>
                      <th className="p-2">ID</th>
                      <th className="p-2 text-right">Days</th>
                      <th className="p-2 text-right">Rate</th>
                      <th className="p-2 text-right">Salary</th>
                      <th className="p-2 text-right">Food</th>
                      <th className="p-2 text-right">Transport</th>
                      <th className="p-2 text-right">Paid</th>
                      <th className="p-2 text-right">Advance</th>
                      <th className="p-2 text-right">Net Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((e, i) => (
                      <tr key={i} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">{e.name}</td>
                        <td className="p-2 text-muted-foreground">{e.employee_id}</td>
                        <td className="p-2 text-right">{e.duty_days}</td>
                        <td className="p-2 text-right">৳{e.daily_rate}</td>
                        <td className="p-2 text-right">৳{e.calculated_salary.toLocaleString()}</td>
                        <td className="p-2 text-right">৳{e.food_total.toLocaleString()}</td>
                        <td className="p-2 text-right">৳{e.transport_total.toLocaleString()}</td>
                        <td className="p-2 text-right">৳{e.salary_paid.toLocaleString()}</td>
                        <td className="p-2 text-right">৳{e.advance_total.toLocaleString()}</td>
                        <td className="p-2 text-right">
                          <Badge variant={e.net_due > 0 ? 'destructive' : 'default'}>
                            ৳{e.net_due.toLocaleString()}
                          </Badge>
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

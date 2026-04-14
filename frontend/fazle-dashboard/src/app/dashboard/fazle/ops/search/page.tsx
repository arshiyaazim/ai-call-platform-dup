'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { opsService, type OpsEmployee, type OpsProgram, type OpsPayment, type OpsAttendance } from '@/services/ops';
import { Search, Loader2, Users, Ship, Banknote, CalendarCheck } from 'lucide-react';

type EntityFilter = 'all' | 'employees' | 'programs' | 'payments' | 'attendance';

export default function OpsSearchPage() {
  const [query, setQuery] = React.useState('');
  const [filter, setFilter] = React.useState<EntityFilter>('all');
  const [loading, setLoading] = React.useState(false);
  const [employees, setEmployees] = React.useState<OpsEmployee[]>([]);
  const [programs, setPrograms] = React.useState<OpsProgram[]>([]);
  const [payments, setPayments] = React.useState<OpsPayment[]>([]);
  const [attendance, setAttendance] = React.useState<OpsAttendance[]>([]);
  const [searched, setSearched] = React.useState(false);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const params: Record<string, string> = { q: query.trim() };
      if (filter !== 'all') params.entity = filter;
      const res = await opsService.search(params);
      setEmployees(res.employees || []);
      setPrograms(res.programs || []);
      setPayments(res.payments || []);
      setAttendance(res.attendance || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') doSearch();
  };

  const filters: { value: EntityFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'employees', label: 'Employees' },
    { value: 'programs', label: 'Programs' },
    { value: 'payments', label: 'Payments' },
    { value: 'attendance', label: 'Attendance' },
  ];

  const totalResults = employees.length + programs.length + payments.length + attendance.length;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Ops Search</h1>

      {/* Search bar */}
      <div className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search by name, ID, vessel, location…"
          className="flex-1"
        />
        <Button onClick={doSearch} disabled={loading || !query.trim()}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4 mr-1" />}
          Search
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        {filters.map((f) => (
          <Badge
            key={f.value}
            variant={filter === f.value ? 'default' : 'outline'}
            className="cursor-pointer"
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </Badge>
        ))}
      </div>

      {searched && !loading && (
        <p className="text-sm text-muted-foreground">{totalResults} result{totalResults !== 1 ? 's' : ''} found</p>
      )}

      {/* Employees */}
      {employees.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <Users className="w-4 h-4" /> Employees ({employees.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {employees.map((e) => (
                <div key={e.id} className="flex items-center justify-between p-2 border rounded-md text-sm">
                  <div>
                    <span className="font-medium">{e.name}</span>
                    <span className="text-muted-foreground ml-2">{e.employee_id}</span>
                  </div>
                  <Badge variant="outline">{e.role}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Programs */}
      {programs.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <Ship className="w-4 h-4" /> Programs ({programs.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {programs.map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2 border rounded-md text-sm">
                  <div>
                    <span className="font-medium">{p.mother_vessel}</span>
                    {p.lighter_vessel && <span className="text-muted-foreground ml-2">→ {p.lighter_vessel}</span>}
                    {p.destination && <span className="text-muted-foreground ml-2">@ {p.destination}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{p.date?.slice(0, 10)}</span>
                    <Badge variant={p.status === 'running' ? 'default' : 'secondary'}>{p.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Payments */}
      {payments.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <Banknote className="w-4 h-4" /> Payments ({payments.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {payments.map((p) => (
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
                    <Badge variant={p.status === 'running' ? 'default' : 'outline'}>{p.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Attendance */}
      {attendance.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <CalendarCheck className="w-4 h-4" /> Attendance ({attendance.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {attendance.map((a) => (
                <div key={a.id} className="flex items-center justify-between p-2 border rounded-md text-sm">
                  <div>
                    <span className="font-medium">{a.name}</span>
                    <span className="text-muted-foreground ml-2">({a.employee_id})</span>
                    {a.location && <span className="text-muted-foreground ml-2">@ {a.location}</span>}
                  </div>
                  <span className="text-xs text-muted-foreground">{a.date?.slice(0, 10)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

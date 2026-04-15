'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  wbomService,
  type WbomEmployee,
  type WbomProgram,
  type WbomTransaction,
} from '@/services/wbom';
import {
  Search,
  RefreshCw,
  Loader2,
  Plus,
  CheckCircle2,
  XCircle,
  Edit,
  Trash2,
  Save,
  X,
  Users,
  Ship,
  Banknote,
  Anchor,
  Phone,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

// ── Tab type ─────────────────────────────────────────────────
type Tab = 'employees' | 'programs' | 'transactions';

export default function WbomPage() {
  const [tab, setTab] = React.useState<Tab>('employees');
  const [message, setMessage] = React.useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">WBOM Dashboard</h1>
        <p className="text-muted-foreground">
          WhatsApp Business Operations Manager — Employees, Escort Duty & Transactions
        </p>
      </div>

      {/* Feedback */}
      {message && (
        <div
          className={`rounded-lg border p-3 flex items-center gap-2 ${
            message.type === 'success'
              ? 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400'
              : 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <XCircle className="h-4 w-4" />
          )}
          <span className="text-sm">{message.text}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {([
          { key: 'employees' as Tab, label: 'Employees', icon: Users },
          { key: 'programs' as Tab, label: 'Escort Duty', icon: Ship },
          { key: 'transactions' as Tab, label: 'Transactions', icon: Banknote },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 'employees' && <EmployeesTab showMsg={showMsg} />}
      {tab === 'programs' && <ProgramsTab showMsg={showMsg} />}
      {tab === 'transactions' && <TransactionsTab showMsg={showMsg} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// EMPLOYEES TAB
// ═══════════════════════════════════════════════════════════════
function EmployeesTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [employees, setEmployees] = React.useState<WbomEmployee[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState('');
  const [editing, setEditing] = React.useState<Partial<WbomEmployee> | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const fetchEmployees = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = search.trim()
        ? await wbomService.searchEmployees(search)
        : await wbomService.listEmployees({ limit: 200 });
      setEmployees(Array.isArray(data) ? data : []);
    } catch {
      showMsg('Failed to load employees', 'error');
    } finally {
      setLoading(false);
    }
  }, [search, showMsg]);

  React.useEffect(() => {
    const t = setTimeout(fetchEmployees, 300);
    return () => clearTimeout(t);
  }, [fetchEmployees]);

  const handleSave = async () => {
    if (!editing) return;
    try {
      if (editing.employee_id) {
        await wbomService.updateEmployee(editing.employee_id, editing);
        showMsg('Employee updated');
      } else {
        await wbomService.createEmployee(editing);
        showMsg('Employee created');
      }
      setDialogOpen(false);
      setEditing(null);
      fetchEmployees();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this employee?')) return;
    try {
      await wbomService.deleteEmployee(id);
      showMsg('Employee deleted');
      fetchEmployees();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'active': return 'bg-green-500/20 text-green-600 dark:text-green-400';
      case 'inactive': return 'bg-gray-500/20 text-gray-600 dark:text-gray-400';
      case 'suspended': return 'bg-red-500/20 text-red-600 dark:text-red-400';
      default: return 'bg-gray-500/20 text-gray-600';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" /> Employees ({employees.length})
          </CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  onClick={() => setEditing({ status: 'active', designation: 'Escort' })}
                >
                  <Plus className="mr-2 h-4 w-4" /> Add Employee
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>
                    {editing?.employee_id ? 'Edit Employee' : 'New Employee'}
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                  <div>
                    <Label>Name</Label>
                    <Input
                      value={editing?.employee_name || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, employee_name: e.target.value }))
                      }
                      placeholder="Full name"
                    />
                  </div>
                  <div>
                    <Label>Mobile</Label>
                    <Input
                      value={editing?.employee_mobile || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, employee_mobile: e.target.value }))
                      }
                      placeholder="01XXXXXXXXX"
                    />
                  </div>
                  <div>
                    <Label>Designation</Label>
                    <Input
                      value={editing?.designation || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, designation: e.target.value }))
                      }
                      placeholder="Escort"
                    />
                  </div>
                  <div>
                    <Label>Status</Label>
                    <select
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                      value={editing?.status || 'active'}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, status: e.target.value }))
                      }
                    >
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="suspended">Suspended</option>
                    </select>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                      <X className="mr-2 h-4 w-4" /> Cancel
                    </Button>
                    <Button onClick={handleSave}>
                      <Save className="mr-2 h-4 w-4" /> Save
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" size="sm" onClick={fetchEmployees}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {/* Search */}
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or mobile..."
            className="pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : employees.length === 0 ? (
          <p className="text-center py-12 text-muted-foreground">No employees found.</p>
        ) : (
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">ID</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Name</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Mobile</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Designation</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Status</th>
                  <th className="h-12 px-4 text-right text-sm font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <tr key={emp.employee_id} className="border-b transition-colors hover:bg-muted/50">
                    <td className="p-4 text-sm font-mono">{emp.employee_id}</td>
                    <td className="p-4 text-sm font-medium">{emp.employee_name}</td>
                    <td className="p-4 text-sm">
                      <span className="flex items-center gap-1">
                        <Phone className="h-3 w-3 text-muted-foreground" />
                        {emp.employee_mobile}
                      </span>
                    </td>
                    <td className="p-4 text-sm">{emp.designation}</td>
                    <td className="p-4 text-sm">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(emp.status)}`}>
                        {emp.status}
                      </span>
                    </td>
                    <td className="p-4 text-sm text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditing(emp);
                            setDialogOpen(true);
                          }}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(emp.employee_id)}
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════
// ESCORT PROGRAMS TAB
// ═══════════════════════════════════════════════════════════════
function ProgramsTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [programs, setPrograms] = React.useState<WbomProgram[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [statusFilter, setStatusFilter] = React.useState('');
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Partial<WbomProgram> | null>(null);

  const fetchPrograms = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await wbomService.listPrograms({
        status: statusFilter || undefined,
        limit: 200,
      });
      setPrograms(Array.isArray(data) ? data : []);
    } catch {
      showMsg('Failed to load programs', 'error');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, showMsg]);

  React.useEffect(() => {
    fetchPrograms();
  }, [fetchPrograms]);

  const handleSave = async () => {
    if (!editing) return;
    try {
      if (editing.program_id) {
        await wbomService.updateProgram(editing.program_id, editing);
        showMsg('Program updated');
      } else {
        await wbomService.createProgram(editing);
        showMsg('Program created');
      }
      setDialogOpen(false);
      setEditing(null);
      fetchPrograms();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this escort program?')) return;
    try {
      await wbomService.deleteProgram(id);
      showMsg('Program deleted');
      fetchPrograms();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'active': return 'bg-green-500/20 text-green-600 dark:text-green-400';
      case 'completed': return 'bg-blue-500/20 text-blue-600 dark:text-blue-400';
      case 'cancelled': return 'bg-red-500/20 text-red-600 dark:text-red-400';
      case 'pending': return 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400';
      default: return 'bg-gray-500/20 text-gray-600';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Ship className="h-5 w-5" /> Escort Duty Programs ({programs.length})
          </CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  onClick={() => setEditing({ status: 'active', shift: 'day' })}
                >
                  <Plus className="mr-2 h-4 w-4" /> Add Program
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>
                    {editing?.program_id ? 'Edit Program' : 'New Escort Program'}
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                  <div>
                    <Label>Mother Vessel</Label>
                    <Input
                      value={editing?.mother_vessel || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, mother_vessel: e.target.value }))
                      }
                      placeholder="MV Star"
                    />
                  </div>
                  <div>
                    <Label>Lighter Vessel</Label>
                    <Input
                      value={editing?.lighter_vessel || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, lighter_vessel: e.target.value }))
                      }
                      placeholder="LV Moon"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Employee ID</Label>
                      <Input
                        type="number"
                        value={editing?.employee_id || ''}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            employee_id: e.target.value ? Number(e.target.value) : undefined,
                          }))
                        }
                        placeholder="ID"
                      />
                    </div>
                    <div>
                      <Label>Contact ID</Label>
                      <Input
                        type="number"
                        value={editing?.contact_id || ''}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            contact_id: e.target.value ? Number(e.target.value) : undefined,
                          }))
                        }
                        placeholder="ID"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Shift</Label>
                      <select
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        value={editing?.shift || 'day'}
                        onChange={(e) =>
                          setEditing((p) => ({ ...p, shift: e.target.value }))
                        }
                      >
                        <option value="day">Day</option>
                        <option value="night">Night</option>
                        <option value="both">Both</option>
                      </select>
                    </div>
                    <div>
                      <Label>Status</Label>
                      <select
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        value={editing?.status || 'active'}
                        onChange={(e) =>
                          setEditing((p) => ({ ...p, status: e.target.value }))
                        }
                      >
                        <option value="active">Active</option>
                        <option value="pending">Pending</option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                    </div>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                      <X className="mr-2 h-4 w-4" /> Cancel
                    </Button>
                    <Button onClick={handleSave}>
                      <Save className="mr-2 h-4 w-4" /> Save
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" size="sm" onClick={fetchPrograms}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {/* Filter */}
        <div className="mt-3 flex gap-2">
          {['', 'active', 'pending', 'completed', 'cancelled'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                statusFilter === s
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : programs.length === 0 ? (
          <p className="text-center py-12 text-muted-foreground">No escort programs found.</p>
        ) : (
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">ID</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Mother Vessel</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Lighter Vessel</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Employee</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Shift</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Status</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Date</th>
                  <th className="h-12 px-4 text-right text-sm font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {programs.map((p) => (
                  <tr key={p.program_id} className="border-b transition-colors hover:bg-muted/50">
                    <td className="p-4 text-sm font-mono">{p.program_id}</td>
                    <td className="p-4 text-sm font-medium">
                      <span className="flex items-center gap-1">
                        <Anchor className="h-3 w-3 text-muted-foreground" />
                        {p.mother_vessel}
                      </span>
                    </td>
                    <td className="p-4 text-sm">{p.lighter_vessel || '—'}</td>
                    <td className="p-4 text-sm">{p.employee_name || `#${p.employee_id || '—'}`}</td>
                    <td className="p-4 text-sm capitalize">{p.shift || '—'}</td>
                    <td className="p-4 text-sm">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(p.status)}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="p-4 text-sm text-muted-foreground">
                      {p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="p-4 text-sm text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditing(p);
                            setDialogOpen(true);
                          }}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(p.program_id)}
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════
// TRANSACTIONS TAB
// ═══════════════════════════════════════════════════════════════
function TransactionsTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [transactions, setTransactions] = React.useState<WbomTransaction[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [methodFilter, setMethodFilter] = React.useState('');
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Partial<WbomTransaction> | null>(null);

  const fetchTransactions = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await wbomService.listTransactions({
        payment_method: methodFilter || undefined,
        limit: 200,
      });
      setTransactions(Array.isArray(data) ? data : []);
    } catch {
      showMsg('Failed to load transactions', 'error');
    } finally {
      setLoading(false);
    }
  }, [methodFilter, showMsg]);

  React.useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const handleSave = async () => {
    if (!editing) return;
    try {
      await wbomService.createTransaction(editing);
      showMsg('Transaction recorded');
      setDialogOpen(false);
      setEditing(null);
      fetchTransactions();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this transaction?')) return;
    try {
      await wbomService.deleteTransaction(id);
      showMsg('Transaction deleted');
      fetchTransactions();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const methodColor = (m: string) => {
    switch (m?.toLowerCase()) {
      case 'cash': return 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400';
      case 'bkash': return 'bg-pink-500/20 text-pink-600 dark:text-pink-400';
      case 'nagad': return 'bg-orange-500/20 text-orange-600 dark:text-orange-400';
      default: return 'bg-gray-500/20 text-gray-600';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Banknote className="h-5 w-5" /> Cash Transactions ({transactions.length})
          </CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  onClick={() =>
                    setEditing({
                      payment_method: 'Cash',
                      transaction_type: 'Advance',
                      transaction_date: new Date().toISOString().split('T')[0],
                    })
                  }
                >
                  <Plus className="mr-2 h-4 w-4" /> Add Transaction
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>New Transaction</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                  <div>
                    <Label>Employee ID</Label>
                    <Input
                      type="number"
                      value={editing?.employee_id || ''}
                      onChange={(e) =>
                        setEditing((p) => ({
                          ...p,
                          employee_id: Number(e.target.value),
                        }))
                      }
                      placeholder="Employee ID"
                    />
                  </div>
                  <div>
                    <Label>Amount (BDT)</Label>
                    <Input
                      type="number"
                      value={editing?.amount || ''}
                      onChange={(e) =>
                        setEditing((p) => ({
                          ...p,
                          amount: Number(e.target.value),
                        }))
                      }
                      placeholder="5000"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Payment Method</Label>
                      <select
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        value={editing?.payment_method || 'Cash'}
                        onChange={(e) =>
                          setEditing((p) => ({ ...p, payment_method: e.target.value }))
                        }
                      >
                        <option value="Cash">Cash</option>
                        <option value="Bkash">Bkash</option>
                        <option value="Nagad">Nagad</option>
                      </select>
                    </div>
                    <div>
                      <Label>Type</Label>
                      <select
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        value={editing?.transaction_type || 'Advance'}
                        onChange={(e) =>
                          setEditing((p) => ({ ...p, transaction_type: e.target.value }))
                        }
                      >
                        <option value="Advance">Advance</option>
                        <option value="Salary">Salary</option>
                        <option value="Deduction">Deduction</option>
                        <option value="Bonus">Bonus</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <Label>Date</Label>
                    <Input
                      type="date"
                      value={editing?.transaction_date || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, transaction_date: e.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <Label>Notes</Label>
                    <Input
                      value={editing?.notes || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, notes: e.target.value }))
                      }
                      placeholder="Optional notes"
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                      <X className="mr-2 h-4 w-4" /> Cancel
                    </Button>
                    <Button onClick={handleSave}>
                      <Save className="mr-2 h-4 w-4" /> Record
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" size="sm" onClick={fetchTransactions}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {/* Filter */}
        <div className="mt-3 flex gap-2">
          {['', 'Cash', 'Bkash', 'Nagad'].map((m) => (
            <button
              key={m}
              onClick={() => setMethodFilter(m)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                methodFilter === m
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {m || 'All'}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : transactions.length === 0 ? (
          <p className="text-center py-12 text-muted-foreground">No transactions found.</p>
        ) : (
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">ID</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Employee</th>
                  <th className="h-12 px-4 text-right text-sm font-medium text-muted-foreground">Amount</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Method</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Type</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Date</th>
                  <th className="h-12 px-4 text-left text-sm font-medium text-muted-foreground">Notes</th>
                  <th className="h-12 px-4 text-right text-sm font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((tx) => (
                  <tr key={tx.transaction_id} className="border-b transition-colors hover:bg-muted/50">
                    <td className="p-4 text-sm font-mono">{tx.transaction_id}</td>
                    <td className="p-4 text-sm">{tx.employee_name || `#${tx.employee_id}`}</td>
                    <td className="p-4 text-sm text-right font-medium tabular-nums">
                      ৳{Number(tx.amount).toLocaleString()}
                    </td>
                    <td className="p-4 text-sm">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${methodColor(tx.payment_method)}`}>
                        {tx.payment_method}
                      </span>
                    </td>
                    <td className="p-4 text-sm">{tx.transaction_type}</td>
                    <td className="p-4 text-sm text-muted-foreground">
                      {tx.transaction_date ? new Date(tx.transaction_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="p-4 text-sm text-muted-foreground max-w-[200px] truncate">
                      {tx.notes || '—'}
                    </td>
                    <td className="p-4 text-sm text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(tx.transaction_id)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

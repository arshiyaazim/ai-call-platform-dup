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
  type SearchSuggestion,
  type FullSearchResult,
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
  ChevronDown,
  ChevronUp,
  Calendar,
  Filter,
  Eye,
  UserCircle,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';

// ── Constants ────────────────────────────────────────────────
const PAGE_SIZE = 20;
type Tab = 'employees' | 'programs' | 'transactions';

// ═══════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════
export default function WbomPage() {
  const [tab, setTab] = React.useState<Tab>('employees');
  const [message, setMessage] = React.useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // ── Global search state ──
  const [globalQuery, setGlobalQuery] = React.useState('');
  const [suggestions, setSuggestions] = React.useState<SearchSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = React.useState(false);
  const [searchResult, setSearchResult] = React.useState<FullSearchResult | null>(null);
  const [searchLoading, setSearchLoading] = React.useState(false);
  const suggestRef = React.useRef<HTMLDivElement>(null);

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  // ── Typeahead ──
  React.useEffect(() => {
    if (globalQuery.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const s = await wbomService.suggest(globalQuery.trim());
        setSuggestions(Array.isArray(s) ? s : []);
        setShowSuggestions(true);
      } catch {
        setSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [globalQuery]);

  // ── Click outside to close suggestions ──
  React.useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (suggestRef.current && !suggestRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const executeSearch = async (query: string, type?: string) => {
    if (!query.trim()) return;
    setSearchLoading(true);
    setShowSuggestions(false);
    try {
      const result = await wbomService.fullSearch(query.trim(), type);
      setSearchResult(result);
    } catch {
      showMsg('Search failed', 'error');
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSuggestionClick = (s: SearchSuggestion) => {
    setGlobalQuery(s.label);
    setShowSuggestions(false);
    executeSearch(s.label, s.type);
  };

  const clearSearch = () => {
    setGlobalQuery('');
    setSearchResult(null);
    setSuggestions([]);
  };

  const suggestionIcon = (type: string) => {
    switch (type) {
      case 'employee': return <UserCircle className="h-4 w-4 text-blue-500" />;
      case 'vessel': return <Anchor className="h-4 w-4 text-emerald-500" />;
      case 'lighter': return <Ship className="h-4 w-4 text-orange-500" />;
      default: return <Search className="h-4 w-4" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">WBOM Dashboard</h1>
        <p className="text-muted-foreground">
          HR &amp; Operations — Employees, Escort Duty &amp; Payroll
        </p>
      </div>

      {/* ── Feedback ── */}
      {message && (
        <div
          className={`rounded-lg border p-3 flex items-center gap-2 ${
            message.type === 'success'
              ? 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400'
              : 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400'
          }`}
        >
          {message.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
          <span className="text-sm">{message.text}</span>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════ */}
      {/* GLOBAL SMART SEARCH                                       */}
      {/* ══════════════════════════════════════════════════════════ */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative" ref={suggestRef}>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search employees, vessels, mobile numbers..."
                  className="pl-10 pr-10 h-11 text-base"
                  value={globalQuery}
                  onChange={(e) => setGlobalQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') executeSearch(globalQuery);
                    if (e.key === 'Escape') setShowSuggestions(false);
                  }}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                />
                {globalQuery && (
                  <button
                    onClick={clearSearch}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              <Button onClick={() => executeSearch(globalQuery)} disabled={searchLoading} className="h-11 px-6">
                {searchLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
                Search
              </Button>
            </div>

            {/* ── Suggestion dropdown ── */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-50 top-full left-0 right-0 mt-1 rounded-lg border bg-popover shadow-lg overflow-hidden">
                {suggestions.map((s, i) => (
                  <button
                    key={`${s.type}-${s.label}-${i}`}
                    onClick={() => handleSuggestionClick(s)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/60 transition-colors border-b last:border-0"
                  >
                    {suggestionIcon(s.type)}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{s.label}</div>
                      <div className="text-xs text-muted-foreground truncate">{s.sublabel}</div>
                    </div>
                    <Badge variant="outline" className="text-[10px] capitalize shrink-0">
                      {s.type}
                    </Badge>
                  </button>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ══════════════════════════════════════════════════════════ */}
      {/* SEARCH RESULTS (shown when search is active)              */}
      {/* ══════════════════════════════════════════════════════════ */}
      {searchResult && (
        <SearchResults result={searchResult} onClose={clearSearch} showMsg={showMsg} />
      )}

      {/* ══════════════════════════════════════════════════════════ */}
      {/* TAB NAVIGATION (hidden when search results shown)         */}
      {/* ══════════════════════════════════════════════════════════ */}
      {!searchResult && (
        <>
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

          {tab === 'employees' && <EmployeesTab showMsg={showMsg} />}
          {tab === 'programs' && <ProgramsTab showMsg={showMsg} />}
          {tab === 'transactions' && <TransactionsTab showMsg={showMsg} />}
        </>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// SEARCH RESULTS VIEW
// ═══════════════════════════════════════════════════════════════
function SearchResults({
  result,
  onClose,
  showMsg,
}: {
  result: FullSearchResult;
  onClose: () => void;
  showMsg: (t: string, tp?: 'success' | 'error') => void;
}) {
  const [expandedEmployee, setExpandedEmployee] = React.useState<number | null>(null);

  const hasEmployees = result.employees.length > 0;
  const hasVesselPrograms = result.vessel_programs.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          Search results for &ldquo;{result.query}&rdquo;
        </h2>
        <Button variant="outline" size="sm" onClick={onClose}>
          <X className="h-4 w-4 mr-1" /> Clear
        </Button>
      </div>

      {/* ── Employee results with expandable detail ── */}
      {hasEmployees && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-5 w-5" /> Employees ({result.employees.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {result.employees.map((emp) => {
              const isExpanded = expandedEmployee === emp.employee_id;
              return (
                <div key={emp.employee_id} className="border rounded-lg overflow-hidden">
                  {/* Employee summary row */}
                  <button
                    onClick={() => setExpandedEmployee(isExpanded ? null : emp.employee_id)}
                    className="w-full flex items-center gap-4 p-4 hover:bg-muted/40 transition-colors text-left"
                  >
                    <UserCircle className="h-10 w-10 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium">{emp.employee_name}</div>
                      <div className="text-sm text-muted-foreground flex items-center gap-3">
                        <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{emp.employee_mobile}</span>
                        <span>{emp.designation}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 shrink-0">
                      <StatusBadge status={emp.status} />
                      <div className="text-right text-sm">
                        <div className="font-medium">{emp.total_programs ?? 0} programs</div>
                        <div className="text-muted-foreground">{emp.total_transactions ?? 0} txns</div>
                      </div>
                      {emp.total_amount != null && (
                        <div className="text-right text-sm font-medium tabular-nums">
                          ৳{Number(emp.total_amount).toLocaleString()}
                        </div>
                      )}
                      {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="border-t bg-muted/20 p-4 space-y-4">
                      {/* Programs */}
                      {emp.programs && emp.programs.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                            <Ship className="h-4 w-4" /> Escort Programs ({emp.programs.length})
                          </h4>
                          <div className="rounded-md border overflow-hidden">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b bg-muted/50">
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Mother Vessel</th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Lighter</th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Shift</th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {emp.programs.map((p) => (
                                  <tr key={p.program_id} className="border-b last:border-0 hover:bg-muted/30">
                                    <td className="px-3 py-2 font-medium">{p.mother_vessel}</td>
                                    <td className="px-3 py-2">{p.lighter_vessel || '—'}</td>
                                    <td className="px-3 py-2 text-muted-foreground">{fmtDate(p.program_date)}</td>
                                    <td className="px-3 py-2"><ShiftBadge shift={p.shift} /></td>
                                    <td className="px-3 py-2"><ProgramStatusBadge status={p.status} /></td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                      {/* Transactions */}
                      {emp.transactions && emp.transactions.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                            <Banknote className="h-4 w-4" /> Transactions ({emp.transactions.length})
                          </h4>
                          <DateGroupedTransactions transactions={emp.transactions} compact />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* ── Vessel search results ── */}
      {hasVesselPrograms && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Anchor className="h-5 w-5" /> Vessel Programs ({result.vessel_programs.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Mother Vessel</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Lighter Vessel</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Employee</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Designation</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Shift</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {result.vessel_programs.map((p) => (
                    <tr key={p.program_id} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-3 py-2 font-medium">
                        <span className="flex items-center gap-1"><Anchor className="h-3 w-3 text-muted-foreground" />{p.mother_vessel}</span>
                      </td>
                      <td className="px-3 py-2">{p.lighter_vessel || '—'}</td>
                      <td className="px-3 py-2">
                        {p.employee_name ? (
                          <span className="flex items-center gap-1">
                            <UserCircle className="h-3 w-3 text-muted-foreground" />
                            {p.employee_name}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{(p as any).designation || '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{fmtDate(p.program_date)}</td>
                      <td className="px-3 py-2"><ShiftBadge shift={p.shift} /></td>
                      <td className="px-3 py-2"><ProgramStatusBadge status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {!hasEmployees && !hasVesselPrograms && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No results found for &ldquo;{result.query}&rdquo;
          </CardContent>
        </Card>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// EMPLOYEES TAB
// ═══════════════════════════════════════════════════════════════
function EmployeesTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [employees, setEmployees] = React.useState<WbomEmployee[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [search, setSearch] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('');
  const [designationFilter, setDesignationFilter] = React.useState('');
  const [showFilters, setShowFilters] = React.useState(false);
  const [editing, setEditing] = React.useState<Partial<WbomEmployee> | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [detailId, setDetailId] = React.useState<number | null>(null);
  const [detailData, setDetailData] = React.useState<WbomEmployee | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  const filters = React.useMemo(() => ({
    status: statusFilter || undefined,
    designation: designationFilter || undefined,
    search: search.trim() || undefined,
  }), [statusFilter, designationFilter, search]);

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [data, countRes] = await Promise.all([
        wbomService.listEmployees({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
        wbomService.countEmployees(filters),
      ]);
      setEmployees(Array.isArray(data) ? data : []);
      setTotal(countRes?.total ?? 0);
    } catch {
      showMsg('Failed to load employees', 'error');
    } finally {
      setLoading(false);
    }
  }, [filters, page, showMsg]);

  React.useEffect(() => {
    const t = setTimeout(fetchData, 300);
    return () => clearTimeout(t);
  }, [fetchData]);

  React.useEffect(() => { setPage(0); }, [search, statusFilter, designationFilter]);

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
      fetchData();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this employee?')) return;
    try {
      await wbomService.deleteEmployee(id);
      showMsg('Employee deleted');
      fetchData();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const openDetail = async (id: number) => {
    setDetailId(id);
    setDetailLoading(true);
    try {
      const d = await wbomService.getEmployeeDetail(id);
      setDetailData(d);
    } catch {
      showMsg('Failed to load employee detail', 'error');
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" /> Employees
              <Badge variant="secondary" className="ml-1">{total}</Badge>
            </CardTitle>
            <div className="flex gap-2">
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" onClick={() => setEditing({ status: 'Active', designation: 'Escort' })}>
                    <Plus className="mr-2 h-4 w-4" /> Add Employee
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{editing?.employee_id ? 'Edit Employee' : 'New Employee'}</DialogTitle>
                  </DialogHeader>
                  <EmployeeForm editing={editing} setEditing={setEditing} onSave={handleSave} onCancel={() => setDialogOpen(false)} />
                </DialogContent>
              </Dialog>
              <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)}>
                <Filter className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={fetchData}>
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

          {/* Advanced filters */}
          {showFilters && (
            <div className="mt-3 flex flex-wrap gap-3 p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-xs">Status</Label>
                <select
                  className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="">All</option>
                  <option value="Active">Active</option>
                  <option value="Inactive">Inactive</option>
                  <option value="On Leave">On Leave</option>
                  <option value="Terminated">Terminated</option>
                </select>
              </div>
              <div>
                <Label className="text-xs">Designation</Label>
                <select
                  className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                  value={designationFilter}
                  onChange={(e) => setDesignationFilter(e.target.value)}
                >
                  <option value="">All</option>
                  <option value="Escort">Escort</option>
                  <option value="Seal-man">Seal-man</option>
                  <option value="Security Guard">Security Guard</option>
                  <option value="Supervisor">Supervisor</option>
                  <option value="Labor">Labor</option>
                </select>
              </div>
              <div className="flex items-end">
                <Button variant="ghost" size="sm" onClick={() => { setStatusFilter(''); setDesignationFilter(''); }}>
                  Clear filters
                </Button>
              </div>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingSpinner />
          ) : employees.length === 0 ? (
            <EmptyState text="No employees found." />
          ) : (
            <>
              <div className="rounded-md border overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Name</th>
                      <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Mobile</th>
                      <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Designation</th>
                      <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Status</th>
                      <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Joined</th>
                      <th className="h-10 px-4 text-right text-xs font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((emp) => (
                      <tr key={emp.employee_id} className="border-b transition-colors hover:bg-muted/50">
                        <td className="p-3 text-sm font-medium">{emp.employee_name}</td>
                        <td className="p-3 text-sm">
                          <span className="flex items-center gap-1">
                            <Phone className="h-3 w-3 text-muted-foreground" />{emp.employee_mobile}
                          </span>
                        </td>
                        <td className="p-3 text-sm">{emp.designation}</td>
                        <td className="p-3 text-sm"><StatusBadge status={emp.status} /></td>
                        <td className="p-3 text-sm text-muted-foreground">{fmtDate(emp.joining_date)}</td>
                        <td className="p-3 text-sm text-right">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="sm" onClick={() => openDetail(emp.employee_id)} title="View detail">
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => { setEditing(emp); setDialogOpen(true); }}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => handleDelete(emp.employee_id)} className="text-red-500 hover:text-red-700">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />
            </>
          )}
        </CardContent>
      </Card>

      {/* ── Employee Detail Dialog ── */}
      <Dialog open={detailId !== null} onOpenChange={(open) => { if (!open) { setDetailId(null); setDetailData(null); } }}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserCircle className="h-5 w-5" /> Employee Detail
            </DialogTitle>
          </DialogHeader>
          {detailLoading ? (
            <LoadingSpinner />
          ) : detailData ? (
            <div className="space-y-6">
              {/* Profile */}
              <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/40">
                <UserCircle className="h-14 w-14 text-muted-foreground" />
                <div className="flex-1">
                  <h3 className="text-lg font-semibold">{detailData.employee_name}</h3>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                    <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{detailData.employee_mobile}</span>
                    <span>{detailData.designation}</span>
                    <StatusBadge status={detailData.status} />
                  </div>
                  {detailData.address && <div className="text-sm text-muted-foreground mt-1">{detailData.address}</div>}
                </div>
                <div className="text-right text-sm">
                  <div><span className="font-medium">{detailData.total_programs ?? 0}</span> programs</div>
                  <div><span className="font-medium">{detailData.total_transactions ?? 0}</span> transactions</div>
                  <div className="font-semibold text-base mt-1">৳{Number(detailData.total_amount ?? 0).toLocaleString()}</div>
                </div>
              </div>

              {/* Programs */}
              {detailData.programs && detailData.programs.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-1"><Ship className="h-4 w-4" /> Programs</h4>
                  <div className="rounded-md border overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">Mother Vessel</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">Lighter</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">Shift</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailData.programs.map((p) => (
                          <tr key={p.program_id} className="border-b last:border-0 hover:bg-muted/30">
                            <td className="px-3 py-2 font-medium">{p.mother_vessel}</td>
                            <td className="px-3 py-2">{p.lighter_vessel || '—'}</td>
                            <td className="px-3 py-2 text-muted-foreground">{fmtDate(p.program_date)}</td>
                            <td className="px-3 py-2"><ShiftBadge shift={p.shift} /></td>
                            <td className="px-3 py-2"><ProgramStatusBadge status={p.status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Transactions */}
              {detailData.transactions && detailData.transactions.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-1"><Banknote className="h-4 w-4" /> Transactions</h4>
                  <DateGroupedTransactions transactions={detailData.transactions} compact />
                </div>
              )}
            </div>
          ) : (
            <EmptyState text="Employee not found." />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}


// ═══════════════════════════════════════════════════════════════
// ESCORT PROGRAMS TAB
// ═══════════════════════════════════════════════════════════════
function ProgramsTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [programs, setPrograms] = React.useState<WbomProgram[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState('');
  const [shiftFilter, setShiftFilter] = React.useState('');
  const [dateFrom, setDateFrom] = React.useState('');
  const [dateTo, setDateTo] = React.useState('');
  const [search, setSearch] = React.useState('');
  const [showFilters, setShowFilters] = React.useState(false);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Partial<WbomProgram> | null>(null);

  const filters = React.useMemo(() => ({
    status: statusFilter || undefined,
    shift: shiftFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    search: search.trim() || undefined,
  }), [statusFilter, shiftFilter, dateFrom, dateTo, search]);

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [data, countRes] = await Promise.all([
        wbomService.listPrograms({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
        wbomService.countPrograms(filters),
      ]);
      setPrograms(Array.isArray(data) ? data : []);
      setTotal(countRes?.total ?? 0);
    } catch {
      showMsg('Failed to load programs', 'error');
    } finally {
      setLoading(false);
    }
  }, [filters, page, showMsg]);

  React.useEffect(() => { fetchData(); }, [fetchData]);
  React.useEffect(() => { setPage(0); }, [statusFilter, shiftFilter, dateFrom, dateTo, search]);

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
      fetchData();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this escort program?')) return;
    try {
      await wbomService.deleteProgram(id);
      showMsg('Program deleted');
      fetchData();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Ship className="h-5 w-5" /> Escort Programs
            <Badge variant="secondary" className="ml-1">{total}</Badge>
          </CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" onClick={() => setEditing({ status: 'Assigned', shift: 'D' })}>
                  <Plus className="mr-2 h-4 w-4" /> Add Program
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{editing?.program_id ? 'Edit Program' : 'New Escort Program'}</DialogTitle>
                </DialogHeader>
                <ProgramForm editing={editing} setEditing={setEditing} onSave={handleSave} onCancel={() => setDialogOpen(false)} />
              </DialogContent>
            </Dialog>
            <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)}>
              <Filter className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={fetchData}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by vessel name..."
            className="pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Advanced filters */}
        {showFilters && (
          <div className="mt-3 flex flex-wrap gap-3 p-3 rounded-lg bg-muted/50">
            <div>
              <Label className="text-xs">Status</Label>
              <select
                className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="Assigned">Assigned</option>
                <option value="Running">Running</option>
                <option value="Completed">Completed</option>
                <option value="Cancelled">Cancelled</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Shift</Label>
              <select
                className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                value={shiftFilter}
                onChange={(e) => setShiftFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="D">Day</option>
                <option value="N">Night</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Date from</Label>
              <Input type="date" className="mt-1" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Date to</Label>
              <Input type="date" className="mt-1" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="flex items-end">
              <Button variant="ghost" size="sm" onClick={() => { setStatusFilter(''); setShiftFilter(''); setDateFrom(''); setDateTo(''); }}>
                Clear
              </Button>
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {loading ? (
          <LoadingSpinner />
        ) : programs.length === 0 ? (
          <EmptyState text="No escort programs found." />
        ) : (
          <>
            <div className="rounded-md border overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Mother Vessel</th>
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Lighter Vessel</th>
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Employee</th>
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Date</th>
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Shift</th>
                    <th className="h-10 px-4 text-left text-xs font-medium text-muted-foreground">Status</th>
                    <th className="h-10 px-4 text-right text-xs font-medium text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {programs.map((p) => (
                    <tr
                      key={p.program_id}
                      className={`border-b transition-colors hover:bg-muted/50 ${
                        p.status === 'Completed' ? 'bg-blue-500/5' : ''
                      }`}
                    >
                      <td className="p-3 text-sm font-medium">
                        <span className="flex items-center gap-1"><Anchor className="h-3 w-3 text-muted-foreground" />{p.mother_vessel}</span>
                      </td>
                      <td className="p-3 text-sm">{p.lighter_vessel || '—'}</td>
                      <td className="p-3 text-sm">{p.employee_name || '—'}</td>
                      <td className="p-3 text-sm text-muted-foreground">{fmtDate(p.program_date)}</td>
                      <td className="p-3 text-sm"><ShiftBadge shift={p.shift} /></td>
                      <td className="p-3 text-sm"><ProgramStatusBadge status={p.status} /></td>
                      <td className="p-3 text-sm text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="sm" onClick={() => { setEditing(p); setDialogOpen(true); }}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete(p.program_id)} className="text-red-500 hover:text-red-700">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />
          </>
        )}
      </CardContent>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════
// TRANSACTIONS TAB — with date-wise grouping
// ═══════════════════════════════════════════════════════════════
function TransactionsTab({ showMsg }: { showMsg: (t: string, tp?: 'success' | 'error') => void }) {
  const [transactions, setTransactions] = React.useState<WbomTransaction[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [methodFilter, setMethodFilter] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('');
  const [dateFrom, setDateFrom] = React.useState('');
  const [dateTo, setDateTo] = React.useState('');
  const [search, setSearch] = React.useState('');
  const [showFilters, setShowFilters] = React.useState(false);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Partial<WbomTransaction> | null>(null);

  const filters = React.useMemo(() => ({
    payment_method: methodFilter || undefined,
    transaction_type: typeFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    search: search.trim() || undefined,
  }), [methodFilter, typeFilter, dateFrom, dateTo, search]);

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [data, countRes] = await Promise.all([
        wbomService.listTransactions({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
        wbomService.countTransactions(filters),
      ]);
      setTransactions(Array.isArray(data) ? data : []);
      setTotal(countRes?.total ?? 0);
    } catch {
      showMsg('Failed to load transactions', 'error');
    } finally {
      setLoading(false);
    }
  }, [filters, page, showMsg]);

  React.useEffect(() => { fetchData(); }, [fetchData]);
  React.useEffect(() => { setPage(0); }, [methodFilter, typeFilter, dateFrom, dateTo, search]);

  const handleSave = async () => {
    if (!editing) return;
    try {
      await wbomService.createTransaction(editing);
      showMsg('Transaction recorded');
      setDialogOpen(false);
      setEditing(null);
      fetchData();
    } catch {
      showMsg('Save failed', 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this transaction?')) return;
    try {
      await wbomService.deleteTransaction(id);
      showMsg('Transaction deleted');
      fetchData();
    } catch {
      showMsg('Delete failed', 'error');
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Banknote className="h-5 w-5" /> Cash Transactions
            <Badge variant="secondary" className="ml-1">{total}</Badge>
          </CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  onClick={() => setEditing({
                    payment_method: 'Cash',
                    transaction_type: 'Advance',
                    transaction_date: new Date().toISOString().split('T')[0],
                  })}
                >
                  <Plus className="mr-2 h-4 w-4" /> Add Transaction
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>New Transaction</DialogTitle>
                </DialogHeader>
                <TransactionForm editing={editing} setEditing={setEditing} onSave={handleSave} onCancel={() => setDialogOpen(false)} />
              </DialogContent>
            </Dialog>
            <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)}>
              <Filter className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={fetchData}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by employee name or notes..."
            className="pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Advanced filters */}
        {showFilters && (
          <div className="mt-3 flex flex-wrap gap-3 p-3 rounded-lg bg-muted/50">
            <div>
              <Label className="text-xs">Payment Method</Label>
              <select
                className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                value={methodFilter}
                onChange={(e) => setMethodFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="Cash">Cash</option>
                <option value="Bkash">Bkash</option>
                <option value="Nagad">Nagad</option>
                <option value="Rocket">Rocket</option>
                <option value="Bank">Bank</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Type</Label>
              <select
                className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="Advance">Advance</option>
                <option value="Food">Food</option>
                <option value="Conveyance">Conveyance</option>
                <option value="Salary">Salary</option>
                <option value="Deduction">Deduction</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Date from</Label>
              <Input type="date" className="mt-1" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Date to</Label>
              <Input type="date" className="mt-1" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="flex items-end">
              <Button variant="ghost" size="sm" onClick={() => { setMethodFilter(''); setTypeFilter(''); setDateFrom(''); setDateTo(''); }}>
                Clear
              </Button>
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {loading ? (
          <LoadingSpinner />
        ) : transactions.length === 0 ? (
          <EmptyState text="No transactions found." />
        ) : (
          <>
            <DateGroupedTransactions
              transactions={transactions}
              onDelete={handleDelete}
            />
            <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />
          </>
        )}
      </CardContent>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════
// DATE-GROUPED TRANSACTIONS COMPONENT
// ═══════════════════════════════════════════════════════════════
function DateGroupedTransactions({
  transactions,
  onDelete,
  compact = false,
}: {
  transactions: WbomTransaction[];
  onDelete?: (id: number) => void;
  compact?: boolean;
}) {
  const grouped = React.useMemo(() => {
    const map: Record<string, WbomTransaction[]> = {};
    for (const tx of transactions) {
      const d = tx.transaction_date || 'Unknown';
      if (!map[d]) map[d] = [];
      map[d].push(tx);
    }
    return Object.entries(map).sort(([a], [b]) => (b > a ? 1 : -1));
  }, [transactions]);

  return (
    <div className="space-y-4">
      {grouped.map(([date, txs]) => {
        const dayTotal = txs.reduce((s, t) => s + Number(t.amount || 0), 0);
        return (
          <div key={date} className="rounded-lg border overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-muted/60">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                {fmtDateFull(date)}
              </div>
              <div className="text-sm">
                <span className="text-muted-foreground">{txs.length} txns &bull; </span>
                <span className="font-semibold tabular-nums">৳{dayTotal.toLocaleString()}</span>
              </div>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {txs.map((tx) => (
                  <tr key={tx.transaction_id} className="border-t hover:bg-muted/30 transition-colors">
                    {!compact && (
                      <td className="px-4 py-2 text-muted-foreground">{tx.employee_name || `#${tx.employee_id}`}</td>
                    )}
                    <td className="px-4 py-2 text-right font-medium tabular-nums">৳{Number(tx.amount).toLocaleString()}</td>
                    <td className="px-4 py-2"><PaymentMethodBadge method={tx.payment_method} /></td>
                    <td className="px-4 py-2 text-muted-foreground">{tx.transaction_type}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs max-w-[150px] truncate">{tx.remarks || ''}</td>
                    {onDelete && (
                      <td className="px-4 py-2 text-right">
                        <Button variant="ghost" size="sm" onClick={() => onDelete(tx.transaction_id)} className="text-red-500 hover:text-red-700 h-7 w-7 p-0">
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// FORM COMPONENTS
// ═══════════════════════════════════════════════════════════════
function EmployeeForm({
  editing,
  setEditing,
  onSave,
  onCancel,
}: {
  editing: Partial<WbomEmployee> | null;
  setEditing: React.Dispatch<React.SetStateAction<Partial<WbomEmployee> | null>>;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4 pt-2">
      <div>
        <Label>Name *</Label>
        <Input value={editing?.employee_name || ''} onChange={(e) => setEditing((p) => ({ ...p, employee_name: e.target.value }))} placeholder="Full name" />
      </div>
      <div>
        <Label>Mobile *</Label>
        <Input value={editing?.employee_mobile || ''} onChange={(e) => setEditing((p) => ({ ...p, employee_mobile: e.target.value }))} placeholder="01XXXXXXXXX" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Designation</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.designation || 'Escort'} onChange={(e) => setEditing((p) => ({ ...p, designation: e.target.value }))}>
            <option value="Escort">Escort</option>
            <option value="Seal-man">Seal-man</option>
            <option value="Security Guard">Security Guard</option>
            <option value="Supervisor">Supervisor</option>
            <option value="Labor">Labor</option>
          </select>
        </div>
        <div>
          <Label>Status</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.status || 'Active'} onChange={(e) => setEditing((p) => ({ ...p, status: e.target.value }))}>
            <option value="Active">Active</option>
            <option value="Inactive">Inactive</option>
            <option value="On Leave">On Leave</option>
            <option value="Terminated">Terminated</option>
          </select>
        </div>
      </div>
      <div>
        <Label>Bank Account</Label>
        <Input value={editing?.bank_account || ''} onChange={(e) => setEditing((p) => ({ ...p, bank_account: e.target.value }))} placeholder="Account number" />
      </div>
      <div>
        <Label>Emergency Contact</Label>
        <Input value={editing?.emergency_contact || ''} onChange={(e) => setEditing((p) => ({ ...p, emergency_contact: e.target.value }))} placeholder="01XXXXXXXXX" />
      </div>
      <div>
        <Label>Address</Label>
        <Input value={editing?.address || ''} onChange={(e) => setEditing((p) => ({ ...p, address: e.target.value }))} placeholder="Address" />
      </div>
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" onClick={onCancel}><X className="mr-2 h-4 w-4" /> Cancel</Button>
        <Button onClick={onSave}><Save className="mr-2 h-4 w-4" /> Save</Button>
      </div>
    </div>
  );
}

function ProgramForm({
  editing,
  setEditing,
  onSave,
  onCancel,
}: {
  editing: Partial<WbomProgram> | null;
  setEditing: React.Dispatch<React.SetStateAction<Partial<WbomProgram> | null>>;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4 pt-2">
      <div>
        <Label>Mother Vessel *</Label>
        <Input value={editing?.mother_vessel || ''} onChange={(e) => setEditing((p) => ({ ...p, mother_vessel: e.target.value }))} placeholder="MV Star" />
      </div>
      <div>
        <Label>Lighter Vessel *</Label>
        <Input value={editing?.lighter_vessel || ''} onChange={(e) => setEditing((p) => ({ ...p, lighter_vessel: e.target.value }))} placeholder="LV Moon" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Master Mobile</Label>
          <Input value={editing?.master_mobile || ''} onChange={(e) => setEditing((p) => ({ ...p, master_mobile: e.target.value }))} placeholder="01XXXXXXXXX" />
        </div>
        <div>
          <Label>Destination</Label>
          <Input value={editing?.destination || ''} onChange={(e) => setEditing((p) => ({ ...p, destination: e.target.value }))} placeholder="Destination" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <Label>Employee ID</Label>
          <Input
            type="number"
            value={editing?.escort_employee_id || ''}
            onChange={(e) => setEditing((p) => ({ ...p, escort_employee_id: e.target.value ? Number(e.target.value) : undefined }))}
            placeholder="ID"
          />
        </div>
        <div>
          <Label>Shift</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.shift || 'D'} onChange={(e) => setEditing((p) => ({ ...p, shift: e.target.value }))}>
            <option value="D">Day</option>
            <option value="N">Night</option>
          </select>
        </div>
        <div>
          <Label>Status</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.status || 'Assigned'} onChange={(e) => setEditing((p) => ({ ...p, status: e.target.value }))}>
            <option value="Assigned">Assigned</option>
            <option value="Running">Running</option>
            <option value="Completed">Completed</option>
            <option value="Cancelled">Cancelled</option>
          </select>
        </div>
      </div>
      <div>
        <Label>Program Date</Label>
        <Input type="date" value={editing?.program_date || ''} onChange={(e) => setEditing((p) => ({ ...p, program_date: e.target.value }))} />
      </div>
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" onClick={onCancel}><X className="mr-2 h-4 w-4" /> Cancel</Button>
        <Button onClick={onSave}><Save className="mr-2 h-4 w-4" /> Save</Button>
      </div>
    </div>
  );
}

function TransactionForm({
  editing,
  setEditing,
  onSave,
  onCancel,
}: {
  editing: Partial<WbomTransaction> | null;
  setEditing: React.Dispatch<React.SetStateAction<Partial<WbomTransaction> | null>>;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4 pt-2">
      <div>
        <Label>Employee ID *</Label>
        <Input type="number" value={editing?.employee_id || ''} onChange={(e) => setEditing((p) => ({ ...p, employee_id: Number(e.target.value) }))} placeholder="Employee ID" />
      </div>
      <div>
        <Label>Amount (BDT) *</Label>
        <Input type="number" value={editing?.amount || ''} onChange={(e) => setEditing((p) => ({ ...p, amount: Number(e.target.value) }))} placeholder="5000" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Payment Method</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.payment_method || 'Cash'} onChange={(e) => setEditing((p) => ({ ...p, payment_method: e.target.value }))}>
            <option value="Cash">Cash</option>
            <option value="Bkash">Bkash</option>
            <option value="Nagad">Nagad</option>
            <option value="Rocket">Rocket</option>
            <option value="Bank">Bank</option>
          </select>
        </div>
        <div>
          <Label>Type</Label>
          <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing?.transaction_type || 'Advance'} onChange={(e) => setEditing((p) => ({ ...p, transaction_type: e.target.value }))}>
            <option value="Advance">Advance</option>
            <option value="Food">Food</option>
            <option value="Conveyance">Conveyance</option>
            <option value="Salary">Salary</option>
            <option value="Deduction">Deduction</option>
            <option value="Other">Other</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Date *</Label>
          <Input type="date" value={editing?.transaction_date || ''} onChange={(e) => setEditing((p) => ({ ...p, transaction_date: e.target.value }))} />
        </div>
        <div>
          <Label>Payment Mobile</Label>
          <Input value={editing?.payment_mobile || ''} onChange={(e) => setEditing((p) => ({ ...p, payment_mobile: e.target.value }))} placeholder="01XXXXXXXXX" />
        </div>
      </div>
      <div>
        <Label>Remarks</Label>
        <Input value={editing?.remarks || ''} onChange={(e) => setEditing((p) => ({ ...p, remarks: e.target.value }))} placeholder="Optional notes" />
      </div>
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" onClick={onCancel}><X className="mr-2 h-4 w-4" /> Cancel</Button>
        <Button onClick={onSave}><Save className="mr-2 h-4 w-4" /> Record</Button>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// SHARED UI COMPONENTS
// ═══════════════════════════════════════════════════════════════

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const start = page * pageSize + 1;
  const end = Math.min((page + 1) * pageSize, total);

  return (
    <div className="flex items-center justify-between mt-4 px-1">
      <div className="text-sm text-muted-foreground">
        Showing {start}–{end} of {total}
      </div>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onPageChange(0)}>
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-3 text-sm font-medium">
          {page + 1} / {totalPages}
        </span>
        <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => onPageChange(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => onPageChange(totalPages - 1)}>
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = {
    Active: 'bg-green-500/20 text-green-600 dark:text-green-400',
    Inactive: 'bg-gray-500/20 text-gray-600 dark:text-gray-400',
    'On Leave': 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    Terminated: 'bg-red-500/20 text-red-600 dark:text-red-400',
  }[status] || 'bg-gray-500/20 text-gray-600';
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

function ProgramStatusBadge({ status }: { status: string }) {
  const cls = {
    Completed: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
    Running: 'bg-green-500/20 text-green-600 dark:text-green-400',
    Assigned: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    Cancelled: 'bg-red-500/20 text-red-600 dark:text-red-400',
  }[status] || 'bg-gray-500/20 text-gray-600';
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

function ShiftBadge({ shift }: { shift?: string }) {
  if (!shift) return <span className="text-muted-foreground">—</span>;
  const isDay = shift === 'D';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${isDay ? 'bg-amber-500/20 text-amber-600' : 'bg-indigo-500/20 text-indigo-400'}`}>
      {isDay ? 'Day' : 'Night'}
    </span>
  );
}

function PaymentMethodBadge({ method }: { method: string }) {
  const cls = {
    Cash: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    Bkash: 'bg-pink-500/20 text-pink-600 dark:text-pink-400',
    Nagad: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
    Rocket: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
    Bank: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  }[method] || 'bg-gray-500/20 text-gray-600';
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{method}</span>;
}

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-12">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="text-center py-12 text-muted-foreground">{text}</p>;
}

// ── Date formatting helpers ──
function fmtDate(d?: string | null): string {
  if (!d) return '—';
  try { return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return d; }
}

function fmtDateFull(d?: string | null): string {
  if (!d || d === 'Unknown') return 'Unknown Date';
  try { return new Date(d).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'long', year: 'numeric' }); }
  catch { return d; }
}
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
                      value={editing?.remarks || ''}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, remarks: e.target.value }))
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
                      {tx.remarks || '—'}
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

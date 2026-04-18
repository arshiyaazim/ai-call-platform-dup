'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  wbomService,
  type MasterContact,
  type RoleCount,
} from '@/services/wbom';
import {
  Search,
  RefreshCw,
  Loader2,
  Users,
  Phone,
  ChevronLeft,
  ChevronRight,
  Edit,
  Save,
  X,
} from 'lucide-react';

const PAGE_SIZE = 20;
const ROLES = ['owner', 'family', 'employee', 'client', 'vendor', 'job_applicant', 'unknown'] as const;
const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-purple-100 text-purple-800',
  family: 'bg-blue-100 text-blue-800',
  employee: 'bg-green-100 text-green-800',
  client: 'bg-yellow-100 text-yellow-800',
  vendor: 'bg-orange-100 text-orange-800',
  job_applicant: 'bg-gray-100 text-gray-700',
  unknown: 'bg-red-100 text-red-700',
};

export default function ContactsMasterPage() {
  const [contacts, setContacts] = React.useState<MasterContact[]>([]);
  const [roles, setRoles] = React.useState<RoleCount[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [search, setSearch] = React.useState('');
  const [roleFilter, setRoleFilter] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [editRole, setEditRole] = React.useState('');
  const [editName, setEditName] = React.useState('');

  const fetchContacts = React.useCallback(async () => {
    setLoading(true);
    try {
      const [data, countData, rolesData] = await Promise.all([
        wbomService.listMasterContacts({
          role: roleFilter || undefined,
          search: search || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
        wbomService.countMasterContacts({
          role: roleFilter || undefined,
          search: search || undefined,
        }),
        wbomService.listRoles(),
      ]);
      setContacts(data);
      setTotal(countData.total);
      setRoles(rolesData);
    } catch (e) {
      console.error('Failed to fetch contacts:', e);
    } finally {
      setLoading(false);
    }
  }, [page, search, roleFilter]);

  React.useEffect(() => { fetchContacts(); }, [fetchContacts]);

  const handleSaveEdit = async (phone: string) => {
    try {
      await wbomService.updateMasterContact(phone, {
        display_name: editName,
        role: editRole,
      });
      setEditingId(null);
      fetchContacts();
    } catch (e) {
      console.error('Failed to update:', e);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Users className="h-6 w-6" /> Contacts Master
        </h1>
        <Button variant="outline" size="sm" onClick={fetchContacts} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      {/* Role summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {roles.map(r => (
          <Card
            key={r.role}
            className={`cursor-pointer transition-all ${roleFilter === r.role ? 'ring-2 ring-primary' : ''}`}
            onClick={() => { setRoleFilter(roleFilter === r.role ? '' : r.role); setPage(0); }}
          >
            <CardContent className="p-3 text-center">
              <Badge className={ROLE_COLORS[r.role] || 'bg-gray-100'}>{r.role}</Badge>
              <p className="text-2xl font-bold mt-1">{r.count}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or phone..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            className="pl-10"
          />
        </div>
        {(search || roleFilter) && (
          <Button variant="ghost" onClick={() => { setSearch(''); setRoleFilter(''); setPage(0); }}>
            Clear
          </Button>
        )}
      </div>

      {/* Contacts table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">
            {total} contacts {roleFilter && `(${roleFilter})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4">Phone</th>
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Role</th>
                  <th className="pb-2 pr-4">Source</th>
                  <th className="pb-2 pr-4">WhatsApp</th>
                  <th className="pb-2 pr-4">Updated</th>
                  <th className="pb-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map(c => (
                  <tr key={c.id} className="border-b hover:bg-muted/50">
                    <td className="py-2 pr-4 font-mono">
                      <Phone className="inline h-3 w-3 mr-1" />
                      {c.canonical_phone}
                    </td>
                    <td className="py-2 pr-4">
                      {editingId === c.id ? (
                        <Input
                          value={editName}
                          onChange={e => setEditName(e.target.value)}
                          className="h-7 text-sm"
                        />
                      ) : (
                        c.display_name || <span className="text-muted-foreground italic">unknown</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      {editingId === c.id ? (
                        <select
                          value={editRole}
                          onChange={e => setEditRole(e.target.value)}
                          className="border rounded px-2 py-1 text-sm"
                        >
                          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                      ) : (
                        <Badge className={ROLE_COLORS[c.role] || 'bg-gray-100'}>{c.role}</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-muted-foreground">{c.source}</td>
                    <td className="py-2 pr-4">{c.is_whatsapp ? '✅' : '—'}</td>
                    <td className="py-2 pr-4 text-muted-foreground text-xs">
                      {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="py-2">
                      {editingId === c.id ? (
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => handleSaveEdit(c.canonical_phone)}>
                            <Save className="h-3 w-3" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => { setEditingId(c.id); setEditRole(c.role); setEditName(c.display_name); }}
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {contacts.length === 0 && (
                  <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">No contacts found</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-muted-foreground">
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
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

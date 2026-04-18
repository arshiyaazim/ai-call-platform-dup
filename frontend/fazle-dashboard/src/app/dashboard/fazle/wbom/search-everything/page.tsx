'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  wbomService,
  type MasterContact,
  type WbomEmployee,
  type MessageHistoryItem,
  type UnifiedSearchResult,
} from '@/services/wbom';
import {
  Search,
  Loader2,
  Users,
  Briefcase,
  MessageSquare,
  Phone,
} from 'lucide-react';

const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-purple-100 text-purple-800',
  family: 'bg-blue-100 text-blue-800',
  employee: 'bg-green-100 text-green-800',
  client: 'bg-yellow-100 text-yellow-800',
  vendor: 'bg-orange-100 text-orange-800',
  job_applicant: 'bg-gray-100 text-gray-700',
  unknown: 'bg-red-100 text-red-700',
};

export default function SearchEverythingPage() {
  const [query, setQuery] = React.useState('');
  const [results, setResults] = React.useState<UnifiedSearchResult | null>(null);
  const [loading, setLoading] = React.useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await wbomService.unifiedSearch(query.trim());
      setResults(data);
    } catch (e) {
      console.error('Search failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const totalResults = results
    ? results.contacts.length + results.employees.length + results.messages.length
    : 0;

  return (
    <div className="space-y-6 p-4">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Search className="h-6 w-6" /> Search Everything
      </h1>

      {/* Search bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search contacts, employees, messages by name or phone..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            className="pl-10"
          />
        </div>
        <Button onClick={handleSearch} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
        </Button>
      </div>

      {results && (
        <p className="text-sm text-muted-foreground">{totalResults} results for &quot;{query}&quot;</p>
      )}

      {/* Contacts results */}
      {results && results.contacts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Users className="h-4 w-4" /> Master Contacts ({results.contacts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {results.contacts.map(c => (
                <div key={c.id} className="flex items-center justify-between p-2 rounded border hover:bg-muted/50">
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono text-sm">{c.canonical_phone}</span>
                    <span className="font-medium">{c.display_name || '—'}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={ROLE_COLORS[c.role] || 'bg-gray-100'}>{c.role}</Badge>
                    {c.is_whatsapp && <Badge variant="outline">WhatsApp</Badge>}
                    <span className="text-xs text-muted-foreground">{c.source}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Employees results */}
      {results && results.employees.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Briefcase className="h-4 w-4" /> Employees ({results.employees.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {results.employees.map(emp => (
                <div key={emp.employee_id} className="flex items-center justify-between p-2 rounded border hover:bg-muted/50">
                  <div className="flex items-center gap-3">
                    <span className="font-medium">{emp.employee_name}</span>
                    <span className="font-mono text-sm text-muted-foreground">{emp.employee_mobile}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{emp.designation}</Badge>
                    <Badge variant={emp.status === 'Active' ? 'default' : 'secondary'}>{emp.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Messages results */}
      {results && results.messages.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <MessageSquare className="h-4 w-4" /> Messages ({results.messages.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {results.messages.map(msg => (
                <div key={msg.id} className="p-2 rounded border hover:bg-muted/50">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                    <span className="font-mono">{msg.canonical_phone}</span>
                    <Badge variant="outline" className="text-xs">{msg.direction}</Badge>
                    <span>{msg.platform}</span>
                    <span>{new Date(msg.created_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm">{msg.message_text}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {results && totalResults === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No results found for &quot;{query}&quot;
          </CardContent>
        </Card>
      )}
    </div>
  );
}

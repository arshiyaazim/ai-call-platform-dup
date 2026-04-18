'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  wbomService,
  type MessageHistoryItem,
} from '@/services/wbom';
import {
  Search,
  RefreshCw,
  Loader2,
  MessageSquare,
  ArrowDownLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Phone,
} from 'lucide-react';

const PAGE_SIZE = 30;

export default function MessageHistoryPage() {
  const [messages, setMessages] = React.useState<MessageHistoryItem[]>([]);
  const [phone, setPhone] = React.useState('');
  const [searchPhone, setSearchPhone] = React.useState('');
  const [contactMessages, setContactMessages] = React.useState<MessageHistoryItem[]>([]);
  const [contactTotal, setContactTotal] = React.useState(0);
  const [contactPage, setContactPage] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [viewMode, setViewMode] = React.useState<'recent' | 'contact'>('recent');

  const fetchRecent = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await wbomService.listRecentMessages({ limit: PAGE_SIZE });
      setMessages(data);
    } catch (e) {
      console.error('Failed to fetch messages:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchContactMessages = React.useCallback(async (ph: string, pg: number) => {
    setLoading(true);
    try {
      const data = await wbomService.getMessageHistory(ph, {
        limit: PAGE_SIZE,
        offset: pg * PAGE_SIZE,
      });
      setContactMessages(data.messages);
      setContactTotal(data.total);
    } catch (e) {
      console.error('Failed to fetch contact messages:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { fetchRecent(); }, [fetchRecent]);

  const handleSearchPhone = () => {
    if (searchPhone.trim()) {
      setViewMode('contact');
      setPhone(searchPhone.trim());
      setContactPage(0);
      fetchContactMessages(searchPhone.trim(), 0);
    }
  };

  const handleClickPhone = (ph: string) => {
    setViewMode('contact');
    setPhone(ph);
    setSearchPhone(ph);
    setContactPage(0);
    fetchContactMessages(ph, 0);
  };

  const contactTotalPages = Math.ceil(contactTotal / PAGE_SIZE);

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="h-6 w-6" /> Message History
        </h1>
        <div className="flex gap-2">
          {viewMode === 'contact' && (
            <Button variant="outline" size="sm" onClick={() => { setViewMode('recent'); fetchRecent(); }}>
              Back to Recent
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => viewMode === 'recent' ? fetchRecent() : fetchContactMessages(phone, contactPage)} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Phone search */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Phone className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Enter phone number to view history..."
            value={searchPhone}
            onChange={e => setSearchPhone(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearchPhone()}
            className="pl-10"
          />
        </div>
        <Button onClick={handleSearchPhone}>
          <Search className="h-4 w-4 mr-2" /> View
        </Button>
      </div>

      {/* Messages */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">
            {viewMode === 'recent'
              ? `Recent Messages (${messages.length})`
              : `${phone} — ${contactTotal} messages`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(viewMode === 'recent' ? messages : contactMessages).map(msg => (
              <div
                key={msg.id}
                className={`flex gap-3 p-3 rounded-lg border ${
                  msg.direction === 'incoming' ? 'bg-blue-50 border-blue-200' : 'bg-green-50 border-green-200'
                }`}
              >
                <div className="flex-shrink-0 mt-1">
                  {msg.direction === 'incoming'
                    ? <ArrowDownLeft className="h-4 w-4 text-blue-500" />
                    : <ArrowUpRight className="h-4 w-4 text-green-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                    <button
                      className="font-mono hover:underline"
                      onClick={() => handleClickPhone(msg.canonical_phone)}
                    >
                      {msg.canonical_phone}
                    </button>
                    {msg.display_name && <span>({msg.display_name})</span>}
                    <Badge variant="outline" className="text-xs">{msg.role_snapshot || msg.role || 'unknown'}</Badge>
                    <span>{msg.platform}</span>
                    <span>{new Date(msg.created_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap break-words">
                    {msg.message_text || <span className="italic text-muted-foreground">(no text)</span>}
                  </p>
                </div>
              </div>
            ))}
            {(viewMode === 'recent' ? messages : contactMessages).length === 0 && (
              <p className="text-center text-muted-foreground py-8">No messages found</p>
            )}
          </div>

          {/* Pagination for contact view */}
          {viewMode === 'contact' && contactTotalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-muted-foreground">
                Page {contactPage + 1} of {contactTotalPages}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={contactPage === 0} onClick={() => { setContactPage(p => p - 1); fetchContactMessages(phone, contactPage - 1); }}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" disabled={contactPage >= contactTotalPages - 1} onClick={() => { setContactPage(p => p + 1); fetchContactMessages(phone, contactPage + 1); }}>
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

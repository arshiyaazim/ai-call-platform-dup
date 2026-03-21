'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  socialService,
  type SocialStats,
  type SocialMessage,
  type SocialPost,
  type SocialContact,
  type Campaign,
  type ScheduledItem,
  type SocialIntegration,
} from '@/services/social';
import {
  MessageCircle, Facebook, Send, Clock, Users, Megaphone,
  Loader2, RefreshCw, Plus, CheckCircle2, XCircle, Bot,
  CalendarClock, BarChart3, UserPlus, Settings, Plug,
  Power, PowerOff, TestTube, Eye, EyeOff, Shield,
} from 'lucide-react';

type Tab = 'integrations' | 'whatsapp' | 'facebook';

export default function SocialPage() {
  const [tab, setTab] = React.useState<Tab>('integrations');
  const [stats, setStats] = React.useState<SocialStats | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [message, setMessage] = React.useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchStats = React.useCallback(async () => {
    try {
      const data = await socialService.getStats();
      setStats(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { fetchStats(); }, [fetchStats]);

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Social Automation</h1>
          <p className="text-muted-foreground">WhatsApp & Facebook bots with AI-powered responses</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); fetchStats(); }}>
          <RefreshCw className="mr-2 h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Feedback */}
      {message && (
        <div className={`rounded-lg border p-3 flex items-center gap-2 ${message.type === 'success' ? 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400' : 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400'}`}>
          {message.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
          <span className="text-sm">{message.text}</span>
        </div>
      )}

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{stats?.total_contacts ?? 0}</p>
              <p className="text-sm text-muted-foreground">Contacts</p>
            </div>
            <Users className="h-5 w-5 text-muted-foreground" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{stats?.whatsapp_messages ?? 0}</p>
              <p className="text-sm text-muted-foreground">WA Messages</p>
            </div>
            <MessageCircle className="h-5 w-5 text-green-500" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{stats?.facebook_posts ?? 0}</p>
              <p className="text-sm text-muted-foreground">FB Posts</p>
            </div>
            <Facebook className="h-5 w-5 text-blue-500" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{stats?.pending_scheduled ?? 0}</p>
              <p className="text-sm text-muted-foreground">Scheduled</p>
            </div>
            <CalendarClock className="h-5 w-5 text-muted-foreground" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{stats?.active_campaigns ?? 0}</p>
              <p className="text-sm text-muted-foreground">Campaigns</p>
            </div>
            <Megaphone className="h-5 w-5 text-muted-foreground" />
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {([
          { key: 'integrations' as const, label: 'Integrations', icon: Settings },
          { key: 'whatsapp' as const, label: 'WhatsApp Bot', icon: MessageCircle },
          { key: 'facebook' as const, label: 'Facebook Bot', icon: Facebook },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === 'integrations' && <IntegrationsTab onMsg={showMsg} />}
      {tab === 'whatsapp' && <WhatsAppTab onMsg={showMsg} />}
      {tab === 'facebook' && <FacebookTab onMsg={showMsg} />}
    </div>
  );
}

/* ─── Integrations Tab ─────────────────────────────────── */

function IntegrationsTab({ onMsg }: { onMsg: (text: string, type?: 'success' | 'error') => void }) {
  const [integrations, setIntegrations] = React.useState<SocialIntegration[]>([]);
  const [loadingInt, setLoadingInt] = React.useState(true);
  const [showSecrets, setShowSecrets] = React.useState<Record<string, boolean>>({});
  const [testing, setTesting] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState<string | null>(null);

  // WhatsApp form
  const [waForm, setWaForm] = React.useState({
    app_id: '', app_secret: '', access_token: '', phone_number: '',
    phone_number_id: '', waba_id: '', verify_token: '', webhook_url: '',
  });

  // Facebook form
  const [fbForm, setFbForm] = React.useState({
    app_id: '', app_secret: '', access_token: '', page_id: '',
    verify_token: '', webhook_url: '',
  });

  const fetchIntegrations = React.useCallback(async () => {
    try {
      const data = await socialService.listIntegrations();
      setIntegrations(data.integrations || []);
      // Pre-fill forms from existing integrations
      const wa = data.integrations?.find((i: SocialIntegration) => i.platform === 'whatsapp');
      if (wa) {
        setWaForm({
          app_id: wa.app_id || '',
          app_secret: '', // masked — don't pre-fill secrets
          access_token: '',
          phone_number: wa.phone_number || '',
          phone_number_id: wa.phone_number_id || '',
          waba_id: wa.waba_id || '',
          verify_token: wa.verify_token || '',
          webhook_url: wa.webhook_url || '',
        });
      }
      const fb = data.integrations?.find((i: SocialIntegration) => i.platform === 'facebook');
      if (fb) {
        setFbForm({
          app_id: fb.app_id || '',
          app_secret: '',
          access_token: '',
          page_id: fb.page_id || '',
          verify_token: fb.verify_token || '',
          webhook_url: fb.webhook_url || '',
        });
      }
    } catch {
      /* ignore */
    } finally {
      setLoadingInt(false);
    }
  }, []);

  React.useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

  const handleSave = async (platform: string) => {
    setSaving(platform);
    try {
      const form = platform === 'whatsapp' ? waForm : fbForm;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const payload: any = { platform };
      for (const [k, v] of Object.entries(form)) {
        if (v) payload[k] = v;
      }
      await socialService.saveIntegration(payload);
      onMsg(`${platform} integration saved`);
      fetchIntegrations();
    } catch {
      onMsg(`Failed to save ${platform} integration`, 'error');
    } finally {
      setSaving(null);
    }
  };

  const handleTest = async (platform: string) => {
    setTesting(platform);
    try {
      const result = await socialService.testIntegration(platform);
      if (result.connected) {
        onMsg(`${platform} connection successful!`);
      } else {
        onMsg(`${platform} connection failed: ${result.error || 'Unknown error'}`, 'error');
      }
    } catch {
      onMsg(`${platform} test failed`, 'error');
    } finally {
      setTesting(null);
    }
  };

  const handleToggle = async (platform: string, enabled: boolean) => {
    try {
      if (enabled) {
        await socialService.disableIntegration(platform);
        onMsg(`${platform} disabled`);
      } else {
        await socialService.enableIntegration(platform);
        onMsg(`${platform} enabled`);
      }
      fetchIntegrations();
    } catch {
      onMsg(`Failed to toggle ${platform}`, 'error');
    }
  };

  const getIntegration = (platform: string) => integrations.find(i => i.platform === platform);

  if (loadingInt) {
    return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* WhatsApp Integration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageCircle className="h-5 w-5 text-green-500" />
              WhatsApp Business Integration
            </CardTitle>
            <div className="flex items-center gap-2">
              {getIntegration('whatsapp') && (
                <>
                  <Badge variant={getIntegration('whatsapp')?.enabled ? 'default' : 'secondary'}>
                    {getIntegration('whatsapp')?.enabled ? <Power className="mr-1 h-3 w-3" /> : <PowerOff className="mr-1 h-3 w-3" />}
                    {getIntegration('whatsapp')?.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => handleToggle('whatsapp', getIntegration('whatsapp')!.enabled)}
                  >
                    {getIntegration('whatsapp')?.enabled ? 'Disable' : 'Enable'}
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>App ID</Label>
              <Input value={waForm.app_id} onChange={(e) => setWaForm({ ...waForm, app_id: e.target.value })} placeholder="Meta App ID" />
            </div>
            <div>
              <Label className="flex items-center gap-1">
                App Secret <Shield className="h-3 w-3 text-muted-foreground" />
              </Label>
              <div className="relative">
                <Input
                  type={showSecrets['wa_secret'] ? 'text' : 'password'}
                  value={waForm.app_secret}
                  onChange={(e) => setWaForm({ ...waForm, app_secret: e.target.value })}
                  placeholder="Leave empty to keep existing"
                />
                <button
                  onClick={() => setShowSecrets(s => ({ ...s, wa_secret: !s.wa_secret }))}
                  className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground"
                  type="button"
                >
                  {showSecrets['wa_secret'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label className="flex items-center gap-1">
                Access Token <Shield className="h-3 w-3 text-muted-foreground" />
              </Label>
              <div className="relative">
                <Input
                  type={showSecrets['wa_token'] ? 'text' : 'password'}
                  value={waForm.access_token}
                  onChange={(e) => setWaForm({ ...waForm, access_token: e.target.value })}
                  placeholder="Leave empty to keep existing"
                />
                <button
                  onClick={() => setShowSecrets(s => ({ ...s, wa_token: !s.wa_token }))}
                  className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground"
                  type="button"
                >
                  {showSecrets['wa_token'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label>Phone Number</Label>
              <Input value={waForm.phone_number} onChange={(e) => setWaForm({ ...waForm, phone_number: e.target.value })} placeholder="+880..." />
            </div>
            <div>
              <Label>Phone Number ID</Label>
              <Input value={waForm.phone_number_id} onChange={(e) => setWaForm({ ...waForm, phone_number_id: e.target.value })} placeholder="Meta Phone Number ID" />
            </div>
            <div>
              <Label>WABA ID</Label>
              <Input value={waForm.waba_id} onChange={(e) => setWaForm({ ...waForm, waba_id: e.target.value })} placeholder="WhatsApp Business Account ID" />
            </div>
            <div>
              <Label>Verify Token</Label>
              <Input value={waForm.verify_token} onChange={(e) => setWaForm({ ...waForm, verify_token: e.target.value })} placeholder="Webhook verify token" />
            </div>
            <div>
              <Label>Webhook URL</Label>
              <Input value={waForm.webhook_url} onChange={(e) => setWaForm({ ...waForm, webhook_url: e.target.value })} placeholder="https://yourdomain.com/api/fazle/social/whatsapp/webhook" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => handleSave('whatsapp')} disabled={saving === 'whatsapp'}>
              {saving === 'whatsapp' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plug className="mr-2 h-4 w-4" />}
              Save WhatsApp
            </Button>
            <Button variant="outline" onClick={() => handleTest('whatsapp')} disabled={testing === 'whatsapp'}>
              {testing === 'whatsapp' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <TestTube className="mr-2 h-4 w-4" />}
              Test Connection
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Facebook Integration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Facebook className="h-5 w-5 text-blue-500" />
              Facebook Page Integration
            </CardTitle>
            <div className="flex items-center gap-2">
              {getIntegration('facebook') && (
                <>
                  <Badge variant={getIntegration('facebook')?.enabled ? 'default' : 'secondary'}>
                    {getIntegration('facebook')?.enabled ? <Power className="mr-1 h-3 w-3" /> : <PowerOff className="mr-1 h-3 w-3" />}
                    {getIntegration('facebook')?.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => handleToggle('facebook', getIntegration('facebook')!.enabled)}
                  >
                    {getIntegration('facebook')?.enabled ? 'Disable' : 'Enable'}
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>App ID</Label>
              <Input value={fbForm.app_id} onChange={(e) => setFbForm({ ...fbForm, app_id: e.target.value })} placeholder="Facebook App ID" />
            </div>
            <div>
              <Label className="flex items-center gap-1">
                App Secret <Shield className="h-3 w-3 text-muted-foreground" />
              </Label>
              <div className="relative">
                <Input
                  type={showSecrets['fb_secret'] ? 'text' : 'password'}
                  value={fbForm.app_secret}
                  onChange={(e) => setFbForm({ ...fbForm, app_secret: e.target.value })}
                  placeholder="Leave empty to keep existing"
                />
                <button
                  onClick={() => setShowSecrets(s => ({ ...s, fb_secret: !s.fb_secret }))}
                  className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground"
                  type="button"
                >
                  {showSecrets['fb_secret'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label className="flex items-center gap-1">
                Page Access Token <Shield className="h-3 w-3 text-muted-foreground" />
              </Label>
              <div className="relative">
                <Input
                  type={showSecrets['fb_token'] ? 'text' : 'password'}
                  value={fbForm.access_token}
                  onChange={(e) => setFbForm({ ...fbForm, access_token: e.target.value })}
                  placeholder="Leave empty to keep existing"
                />
                <button
                  onClick={() => setShowSecrets(s => ({ ...s, fb_token: !s.fb_token }))}
                  className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground"
                  type="button"
                >
                  {showSecrets['fb_token'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label>Page ID</Label>
              <Input value={fbForm.page_id} onChange={(e) => setFbForm({ ...fbForm, page_id: e.target.value })} placeholder="Facebook Page ID" />
            </div>
            <div>
              <Label>Verify Token</Label>
              <Input value={fbForm.verify_token} onChange={(e) => setFbForm({ ...fbForm, verify_token: e.target.value })} placeholder="Webhook verify token" />
            </div>
            <div>
              <Label>Webhook URL</Label>
              <Input value={fbForm.webhook_url} onChange={(e) => setFbForm({ ...fbForm, webhook_url: e.target.value })} placeholder="https://yourdomain.com/api/fazle/social/facebook/webhook" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => handleSave('facebook')} disabled={saving === 'facebook'}>
              {saving === 'facebook' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plug className="mr-2 h-4 w-4" />}
              Save Facebook
            </Button>
            <Button variant="outline" onClick={() => handleTest('facebook')} disabled={testing === 'facebook'}>
              {testing === 'facebook' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <TestTube className="mr-2 h-4 w-4" />}
              Test Connection
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ─── WhatsApp Tab ─────────────────────────────────────── */

function WhatsAppTab({ onMsg }: { onMsg: (text: string, type?: 'success' | 'error') => void }) {
  const [messages, setMessages] = React.useState<SocialMessage[]>([]);
  const [scheduled, setScheduled] = React.useState<ScheduledItem[]>([]);
  const [contacts, setContacts] = React.useState<SocialContact[]>([]);
  const [loadingMsgs, setLoadingMsgs] = React.useState(true);

  // Send form
  const [to, setTo] = React.useState('');
  const [msgText, setMsgText] = React.useState('');
  const [autoReply, setAutoReply] = React.useState(false);
  const [sending, setSending] = React.useState(false);

  // Schedule form
  const [showSchedule, setShowSchedule] = React.useState(false);
  const [schedTo, setSchedTo] = React.useState('');
  const [schedMsg, setSchedMsg] = React.useState('');
  const [schedAt, setSchedAt] = React.useState('');

  // Broadcast form
  const [showBroadcast, setShowBroadcast] = React.useState(false);
  const [broadcastMsg, setBroadcastMsg] = React.useState('');
  const [broadcastContacts, setBroadcastContacts] = React.useState<string[]>([]);
  const [broadcastName, setBroadcastName] = React.useState('');

  // Add contact
  const [showAddContact, setShowAddContact] = React.useState(false);
  const [newContact, setNewContact] = React.useState({ name: '', identifier: '' });

  const fetchAll = React.useCallback(async () => {
    try {
      const [msgData, schedData, contactData] = await Promise.all([
        socialService.whatsappMessages(),
        socialService.whatsappScheduled(),
        socialService.listContacts('whatsapp'),
      ]);
      setMessages(msgData.messages || []);
      setScheduled(schedData.scheduled || []);
      setContacts(contactData.contacts || []);
    } catch {
      /* ignore */
    } finally {
      setLoadingMsgs(false);
    }
  }, []);

  React.useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSend = async () => {
    if (!to.trim() || !msgText.trim()) return;
    setSending(true);
    try {
      await socialService.whatsappSend(to.trim(), msgText.trim(), autoReply);
      onMsg('Message sent');
      setTo('');
      setMsgText('');
      fetchAll();
    } catch {
      onMsg('Send failed', 'error');
    } finally {
      setSending(false);
    }
  };

  const handleSchedule = async () => {
    if (!schedTo.trim() || !schedMsg.trim() || !schedAt) return;
    try {
      await socialService.whatsappSchedule({ to: schedTo.trim(), message: schedMsg.trim(), scheduled_at: schedAt });
      onMsg('Message scheduled');
      setShowSchedule(false);
      setSchedTo('');
      setSchedMsg('');
      setSchedAt('');
      fetchAll();
    } catch {
      onMsg('Schedule failed', 'error');
    }
  };

  const handleBroadcast = async () => {
    if (broadcastContacts.length === 0 || !broadcastMsg.trim()) return;
    try {
      await socialService.whatsappBroadcast({
        contacts: broadcastContacts,
        message: broadcastMsg.trim(),
        name: broadcastName.trim() || undefined,
      });
      onMsg(`Broadcast queued to ${broadcastContacts.length} contacts`);
      setShowBroadcast(false);
      setBroadcastMsg('');
      setBroadcastContacts([]);
      setBroadcastName('');
    } catch {
      onMsg('Broadcast failed', 'error');
    }
  };

  const handleAddContact = async () => {
    if (!newContact.name.trim() || !newContact.identifier.trim()) return;
    try {
      await socialService.addContact({ name: newContact.name.trim(), platform: 'whatsapp', identifier: newContact.identifier.trim() });
      onMsg('Contact added');
      setShowAddContact(false);
      setNewContact({ name: '', identifier: '' });
      fetchAll();
    } catch {
      onMsg('Failed to add contact', 'error');
    }
  };

  if (loadingMsgs) {
    return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-4">
      {/* Send Message */}
      <Card>
        <CardHeader><CardTitle className="text-base">Send WhatsApp Message</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>To (phone number)</Label>
              <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="+880..." />
            </div>
            <div className="flex items-end gap-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={autoReply} onChange={(e) => setAutoReply(e.target.checked)} className="rounded" />
                <Bot className="h-4 w-4" /> AI Auto-Reply
              </label>
            </div>
          </div>
          <Textarea value={msgText} onChange={(e) => setMsgText(e.target.value)} placeholder="Type your message..." rows={2} />
          <div className="flex gap-2">
            <Button onClick={handleSend} disabled={sending || !to.trim() || !msgText.trim()}>
              {sending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              Send
            </Button>
            <Button variant="outline" onClick={() => setShowSchedule(!showSchedule)}>
              <Clock className="mr-2 h-4 w-4" /> Schedule
            </Button>
            <Button variant="outline" onClick={() => setShowBroadcast(!showBroadcast)}>
              <Megaphone className="mr-2 h-4 w-4" /> Broadcast
            </Button>
            <Button variant="outline" onClick={() => setShowAddContact(!showAddContact)}>
              <UserPlus className="mr-2 h-4 w-4" /> Add Contact
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Schedule Form */}
      {showSchedule && (
        <Card>
          <CardHeader><CardTitle className="text-base">Schedule Message</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-3">
              <div><Label>To</Label><Input value={schedTo} onChange={(e) => setSchedTo(e.target.value)} placeholder="+880..." /></div>
              <div><Label>Message</Label><Input value={schedMsg} onChange={(e) => setSchedMsg(e.target.value)} placeholder="Message text" /></div>
              <div><Label>Schedule At</Label><Input type="datetime-local" value={schedAt} onChange={(e) => setSchedAt(e.target.value)} /></div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSchedule} disabled={!schedTo.trim() || !schedMsg.trim() || !schedAt}>
                <CalendarClock className="mr-2 h-4 w-4" /> Schedule
              </Button>
              <Button variant="outline" onClick={() => setShowSchedule(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Broadcast Form */}
      {showBroadcast && (
        <Card>
          <CardHeader><CardTitle className="text-base">Broadcast Message</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Campaign Name (optional)</Label>
              <Input value={broadcastName} onChange={(e) => setBroadcastName(e.target.value)} placeholder="Weekly Update" />
            </div>
            <Textarea value={broadcastMsg} onChange={(e) => setBroadcastMsg(e.target.value)} placeholder="Broadcast message..." rows={2} />
            <div>
              <Label>Select Contacts ({broadcastContacts.length} selected)</Label>
              <div className="border rounded-lg p-2 max-h-40 overflow-y-auto space-y-1 mt-1">
                {contacts.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-2">No contacts. Add contacts first.</p>
                ) : contacts.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 text-sm cursor-pointer py-1 px-1 hover:bg-muted rounded">
                    <input
                      type="checkbox"
                      checked={broadcastContacts.includes(c.identifier)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setBroadcastContacts([...broadcastContacts, c.identifier]);
                        } else {
                          setBroadcastContacts(broadcastContacts.filter(id => id !== c.identifier));
                        }
                      }}
                      className="rounded"
                    />
                    <span className="font-medium">{c.name}</span>
                    <span className="text-xs text-muted-foreground">{c.identifier}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleBroadcast} disabled={broadcastContacts.length === 0 || !broadcastMsg.trim()}>
                <Megaphone className="mr-2 h-4 w-4" /> Send Broadcast
              </Button>
              <Button variant="outline" onClick={() => setShowBroadcast(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add Contact Form */}
      {showAddContact && (
        <Card>
          <CardHeader><CardTitle className="text-base">Add WhatsApp Contact</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div><Label>Name</Label><Input value={newContact.name} onChange={(e) => setNewContact({ ...newContact, name: e.target.value })} placeholder="Contact name" /></div>
              <div><Label>Phone Number</Label><Input value={newContact.identifier} onChange={(e) => setNewContact({ ...newContact, identifier: e.target.value })} placeholder="+880..." /></div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleAddContact} disabled={!newContact.name.trim() || !newContact.identifier.trim()}>
                <UserPlus className="mr-2 h-4 w-4" /> Add
              </Button>
              <Button variant="outline" onClick={() => setShowAddContact(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Contacts */}
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4" /> Contacts ({contacts.length})</CardTitle></CardHeader>
          <CardContent>
            {contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No contacts yet</p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {contacts.map((c) => (
                  <div key={c.id} className="flex items-center justify-between text-sm py-1">
                    <span className="font-medium">{c.name}</span>
                    <span className="text-xs text-muted-foreground font-mono">{c.identifier}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Scheduled */}
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4" /> Scheduled ({scheduled.length})</CardTitle></CardHeader>
          <CardContent>
            {scheduled.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No scheduled messages</p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {scheduled.map((s) => (
                  <div key={s.id} className="text-sm py-1 border-b last:border-0">
                    <div className="flex justify-between">
                      <Badge variant="outline" className="text-xs">{s.action_type}</Badge>
                      <span className="text-xs text-muted-foreground">{new Date(s.scheduled_at).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Message History */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><MessageCircle className="h-4 w-4" /> Recent Messages</CardTitle></CardHeader>
        <CardContent>
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No messages yet</p>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {messages.map((m) => (
                <div key={m.id} className={`rounded-lg p-3 text-sm ${m.direction === 'outgoing' ? 'bg-primary/10 ml-8' : 'bg-muted mr-8'}`}>
                  <div className="flex justify-between mb-1">
                    <span className="text-xs font-medium">{m.direction === 'outgoing' ? 'Sent' : 'Received'} → {m.contact_identifier}</span>
                    <Badge variant="outline" className="text-xs">{m.status}</Badge>
                  </div>
                  <p>{m.content || m.message_text}</p>
                  {m.ai_response && (
                    <div className="mt-1 pt-1 border-t text-xs text-muted-foreground">
                      <Bot className="inline h-3 w-3 mr-1" />AI: {m.ai_response}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground mt-1">{new Date(m.created_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/* ─── Facebook Tab ─────────────────────────────────────── */

function FacebookTab({ onMsg }: { onMsg: (text: string, type?: 'success' | 'error') => void }) {
  const [posts, setPosts] = React.useState<SocialPost[]>([]);
  const [scheduled, setScheduled] = React.useState<ScheduledItem[]>([]);
  const [loadingPosts, setLoadingPosts] = React.useState(true);

  // Post form
  const [content, setContent] = React.useState('');
  const [imageUrl, setImageUrl] = React.useState('');
  const [aiGenerate, setAiGenerate] = React.useState(false);
  const [prompt, setPrompt] = React.useState('');
  const [scheduleAt, setScheduleAt] = React.useState('');
  const [posting, setPosting] = React.useState(false);

  // Comment form
  const [showComment, setShowComment] = React.useState(false);
  const [commentTarget, setCommentTarget] = React.useState('');
  const [commentMsg, setCommentMsg] = React.useState('');
  const [commentAutoReply, setCommentAutoReply] = React.useState(false);

  // React form
  const [showReact, setShowReact] = React.useState(false);
  const [reactTarget, setReactTarget] = React.useState('');
  const [reactType, setReactType] = React.useState('LIKE');

  const fetchAll = React.useCallback(async () => {
    try {
      const [postData, schedData] = await Promise.all([
        socialService.facebookPosts(),
        socialService.facebookScheduled(),
      ]);
      setPosts(postData.posts || []);
      setScheduled(schedData.scheduled || []);
    } catch {
      /* ignore */
    } finally {
      setLoadingPosts(false);
    }
  }, []);

  React.useEffect(() => { fetchAll(); }, [fetchAll]);

  const handlePost = async () => {
    if (!aiGenerate && !content.trim()) return;
    if (aiGenerate && !prompt.trim()) return;
    setPosting(true);
    try {
      const res = await socialService.facebookPost({
        content: content.trim() || undefined,
        prompt: aiGenerate ? prompt.trim() : undefined,
        ai_generate: aiGenerate,
        image_url: imageUrl.trim() || undefined,
        schedule_at: scheduleAt || undefined,
      });
      onMsg(scheduleAt ? 'Post scheduled' : `Post ${res.status}`);
      setContent('');
      setPrompt('');
      setImageUrl('');
      setScheduleAt('');
      fetchAll();
    } catch {
      onMsg('Post failed', 'error');
    } finally {
      setPosting(false);
    }
  };

  const handleComment = async () => {
    if (!commentTarget.trim() || (!commentMsg.trim() && !commentAutoReply)) return;
    try {
      await socialService.facebookComment({
        post_id: commentTarget.trim(),
        message: commentMsg.trim() || undefined,
        auto_reply: commentAutoReply,
        original_comment: commentAutoReply ? commentMsg.trim() : undefined,
      });
      onMsg('Comment sent');
      setShowComment(false);
      setCommentTarget('');
      setCommentMsg('');
    } catch {
      onMsg('Comment failed', 'error');
    }
  };

  const handleReact = async () => {
    if (!reactTarget.trim()) return;
    try {
      await socialService.facebookReact(reactTarget.trim(), reactType);
      onMsg(`Reacted with ${reactType}`);
      setShowReact(false);
      setReactTarget('');
    } catch {
      onMsg('React failed', 'error');
    }
  };

  if (loadingPosts) {
    return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-4">
      {/* Create Post */}
      <Card>
        <CardHeader><CardTitle className="text-base">Create Facebook Post</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={aiGenerate} onChange={(e) => setAiGenerate(e.target.checked)} className="rounded" />
            <Bot className="h-4 w-4" /> AI-Generate Content
          </label>

          {aiGenerate ? (
            <div>
              <Label>AI Prompt</Label>
              <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the post you want AI to generate..." rows={3} />
            </div>
          ) : (
            <div>
              <Label>Post Content</Label>
              <Textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Write your post..." rows={3} />
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>Image URL (optional)</Label>
              <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://..." />
            </div>
            <div>
              <Label>Schedule (optional)</Label>
              <Input type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} />
            </div>
          </div>

          <div className="flex gap-2">
            <Button onClick={handlePost} disabled={posting || (aiGenerate ? !prompt.trim() : !content.trim())}>
              {posting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              {scheduleAt ? 'Schedule Post' : 'Publish Now'}
            </Button>
            <Button variant="outline" onClick={() => setShowComment(!showComment)}>
              <MessageCircle className="mr-2 h-4 w-4" /> Comment
            </Button>
            <Button variant="outline" onClick={() => setShowReact(!showReact)}>
              <Plus className="mr-2 h-4 w-4" /> React
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Comment Form */}
      {showComment && (
        <Card>
          <CardHeader><CardTitle className="text-base">Reply to Comment</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label>Post/Comment ID</Label>
                <Input value={commentTarget} onChange={(e) => setCommentTarget(e.target.value)} placeholder="Post or Comment ID" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={commentAutoReply} onChange={(e) => setCommentAutoReply(e.target.checked)} className="rounded" />
                  <Bot className="h-4 w-4" /> AI Auto-Reply
                </label>
              </div>
            </div>
            <Textarea value={commentMsg} onChange={(e) => setCommentMsg(e.target.value)} placeholder={commentAutoReply ? "Original comment text for AI to reply to..." : "Your reply..."} rows={2} />
            <div className="flex gap-2">
              <Button onClick={handleComment} disabled={!commentTarget.trim()}>
                <Send className="mr-2 h-4 w-4" /> Send Reply
              </Button>
              <Button variant="outline" onClick={() => setShowComment(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* React Form */}
      {showReact && (
        <Card>
          <CardHeader><CardTitle className="text-base">React to Post</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label>Post/Comment ID</Label>
                <Input value={reactTarget} onChange={(e) => setReactTarget(e.target.value)} placeholder="Target ID" />
              </div>
              <div>
                <Label>Reaction</Label>
                <select
                  value={reactType}
                  onChange={(e) => setReactType(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm bg-background"
                >
                  <option value="LIKE">LIKE</option>
                  <option value="LOVE">LOVE</option>
                  <option value="HAHA">HAHA</option>
                  <option value="WOW">WOW</option>
                  <option value="SAD">SAD</option>
                  <option value="ANGRY">ANGRY</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleReact} disabled={!reactTarget.trim()}>
                React
              </Button>
              <Button variant="outline" onClick={() => setShowReact(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Scheduled */}
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4" /> Scheduled Posts ({scheduled.length})</CardTitle></CardHeader>
          <CardContent>
            {scheduled.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No scheduled posts</p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {scheduled.map((s) => (
                  <div key={s.id} className="text-sm py-2 border-b last:border-0">
                    <div className="flex justify-between">
                      <Badge variant="outline" className="text-xs">{s.action_type}</Badge>
                      <span className="text-xs text-muted-foreground">{new Date(s.scheduled_at).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Stats */}
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Post Stats</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm">Total Posts</span>
                <span className="text-lg font-bold">{posts.length}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm">Published</span>
                <span className="font-medium">{posts.filter(p => p.status === 'published').length}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm">Draft</span>
                <span className="font-medium">{posts.filter(p => p.status === 'draft').length}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Posts List */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Facebook className="h-4 w-4" /> Recent Posts</CardTitle></CardHeader>
        <CardContent>
          {posts.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No posts yet</p>
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {posts.map((p) => (
                <div key={p.id} className="rounded-lg border p-3 text-sm">
                  <div className="flex justify-between mb-2">
                    <Badge variant={p.status === 'published' ? 'default' : 'secondary'}>{p.status}</Badge>
                    <span className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleString()}</span>
                  </div>
                  <p className="line-clamp-3">{p.content}</p>
                  {p.image_url && <p className="text-xs text-blue-500 mt-1 truncate">{p.image_url}</p>}
                  {p.post_id && <p className="text-xs text-muted-foreground mt-1">ID: {p.post_id}</p>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

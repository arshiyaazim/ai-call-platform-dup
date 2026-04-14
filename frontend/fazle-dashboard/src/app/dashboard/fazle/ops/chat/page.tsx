'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { opsService } from '@/services/ops';
import { Send, Loader2, Bot, User } from 'lucide-react';

interface ChatEntry {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  intent?: string;
  timestamp: string;
}

export default function OpsChatPage() {
  const [input, setInput] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const [history, setHistory] = React.useState<ChatEntry[]>([]);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  let nextId = React.useRef(1);

  const scrollBottom = () => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userEntry: ChatEntry = {
      id: nextId.current++,
      role: 'user',
      text,
      timestamp: new Date().toLocaleTimeString(),
    };
    setHistory((h) => [...h, userEntry]);
    setInput('');
    setSending(true);
    scrollBottom();

    try {
      const res = await opsService.simulateMessage(text);
      const botEntry: ChatEntry = {
        id: nextId.current++,
        role: 'assistant',
        text: res.reply || (res.handled ? 'Done.' : '💬 Conversational — forwarded to AI brain.'),
        intent: res.intent,
        timestamp: new Date().toLocaleTimeString(),
      };
      setHistory((h) => [...h, botEntry]);
    } catch (err: unknown) {
      setHistory((h) => [
        ...h,
        {
          id: nextId.current++,
          role: 'assistant',
          text: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setSending(false);
      scrollBottom();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Ops Chat Panel</h1>
      <p className="text-sm text-muted-foreground">
        Simulate WhatsApp messages. Type ops commands like payments, programs, employee registration.
      </p>

      <Card className="flex flex-col h-[calc(100vh-260px)]">
        <CardHeader className="pb-2 border-b">
          <CardTitle className="text-sm">Message Log</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto p-4 space-y-3">
          {history.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-12">
              <Bot className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Send a message to get started.</p>
              <p className="text-xs mt-1">
                Examples: &quot;01711123456 5000 bkash&quot; · &quot;mv ocean star chittagong&quot; · &quot;search rahim&quot;
              </p>
            </div>
          )}

          {history.map((entry) => (
            <div
              key={entry.id}
              className={`flex gap-2 ${
                entry.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {entry.role === 'assistant' && (
                <Bot className="w-6 h-6 mt-1 text-blue-500 shrink-0" />
              )}
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                  entry.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted'
                }`}
              >
                {entry.text}
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] opacity-60">{entry.timestamp}</span>
                  {entry.intent && (
                    <Badge variant="outline" className="text-[10px] h-4">
                      {entry.intent}
                    </Badge>
                  )}
                </div>
              </div>
              {entry.role === 'user' && (
                <User className="w-6 h-6 mt-1 text-muted-foreground shrink-0" />
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </CardContent>

        <div className="border-t p-3 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type ops message… (e.g. 01711123456 5000 bkash)"
            disabled={sending}
            className="flex-1"
          />
          <Button onClick={handleSend} disabled={sending || !input.trim()}>
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </Button>
        </div>
      </Card>
    </div>
  );
}

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Brain,
  Bot,
  Wrench,
  CalendarClock,
  UserCog,
  ScrollText,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Zap,
  Network,
  PlayCircle,
  Lightbulb,
  Settings,
  ShieldAlert,
  Activity,
  GitBranch,
  Store,
  Shield,
  ShieldCheck,
  Users,
  MessageCircle,
  BookUser,
  Database,
  Ship,
  Search,
  MessageSquare,
  DollarSign,
  Wallet,
  Bell,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSidebarStore } from '@/store/sidebar';
import { Button } from '@/components/ui/button';

const navItems = [
  { href: '/dashboard/fazle', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/fazle/memory', label: 'Memory', icon: Brain },
  { href: '/dashboard/fazle/agents', label: 'Agents', icon: Bot },
  { href: '/dashboard/fazle/tools', label: 'Tools', icon: Wrench },
  { href: '/dashboard/fazle/tasks', label: 'Tasks', icon: CalendarClock },
  { href: '/dashboard/fazle/persona', label: 'Persona', icon: UserCog },
  { href: '/dashboard/fazle/autonomy', label: 'Autonomy', icon: Zap },
  { href: '/dashboard/fazle/knowledge-graph', label: 'Knowledge Graph', icon: Network },
  { href: '/dashboard/fazle/autonomous-tasks', label: 'Auto Tasks', icon: PlayCircle },
  { href: '/dashboard/fazle/learning', label: 'Learning', icon: Lightbulb },
  { href: '/dashboard/fazle/ai-safety', label: 'AI Safety', icon: ShieldAlert },
  { href: '/dashboard/fazle/observability', label: 'Observability', icon: Activity },
  { href: '/dashboard/fazle/workflows', label: 'Workflows', icon: GitBranch },
  { href: '/dashboard/fazle/tool-marketplace', label: 'Marketplace', icon: Store },
  { href: '/dashboard/fazle/watchdog', label: 'Watchdog', icon: Shield },
  { href: '/dashboard/fazle/users', label: 'Users', icon: Users },
  { href: '/dashboard/fazle/social', label: 'Social', icon: MessageCircle },
  { href: '/dashboard/fazle/contacts', label: 'Contacts', icon: BookUser },
  { href: '/dashboard/fazle/privacy', label: 'Privacy', icon: ShieldCheck },
  { href: '/dashboard/fazle/gdpr-admin', label: 'GDPR Admin', icon: Shield },
  { href: '/dashboard/fazle/database-maintenance', label: 'DB Maintenance', icon: Database },
  { href: '/dashboard/fazle/ops', label: 'Ops Dashboard', icon: Ship },
  { href: '/dashboard/fazle/ops/chat', label: 'Ops Chat', icon: MessageSquare },
  { href: '/dashboard/fazle/ops/search', label: 'Ops Search', icon: Search },
  { href: '/dashboard/fazle/ops/billing', label: 'Ops Billing', icon: DollarSign },
  { href: '/dashboard/fazle/ops/salary', label: 'Ops Salary', icon: Wallet },
  { href: '/dashboard/fazle/ops/alerts', label: 'Ops Alerts', icon: Bell },
  { href: '/dashboard/fazle/logs', label: 'Logs', icon: ScrollText },
  { href: '/dashboard/fazle/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebarStore();

  return (
    <aside
      className={cn(
        'flex h-screen flex-col border-r bg-card transition-all duration-300',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Header */}
      <div className="flex h-16 items-center border-b px-4">
        <Sparkles className="h-6 w-6 shrink-0 text-primary" />
        {!collapsed && (
          <span className="ml-3 text-lg font-bold tracking-tight">Fazle AI</span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        <p
          className={cn(
            'mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground',
            collapsed && 'sr-only'
          )}
        >
          Fazle AI
        </p>
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== '/dashboard/fazle' && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
              title={collapsed ? item.label : undefined}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Toggle */}
      <div className="border-t p-3">
        <Button variant="ghost" size="sm" className="w-full justify-center" onClick={toggle}>
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
    </aside>
  );
}

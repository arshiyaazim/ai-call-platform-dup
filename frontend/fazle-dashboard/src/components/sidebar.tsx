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
  { href: '/dashboard/fazle/logs', label: 'Logs', icon: ScrollText },
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

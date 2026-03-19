'use client';

import { Moon, Sun, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/auth';
import * as React from 'react';

export function Header() {
  const { logout } = useAuthStore();
  const [dark, setDark] = React.useState(false);

  React.useEffect(() => {
    const isDark = document.documentElement.classList.contains('dark');
    setDark(isDark);
  }, []);

  const toggleTheme = () => {
    document.documentElement.classList.toggle('dark');
    setDark((d) => !d);
  };

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <h1 className="text-lg font-semibold">Fazle AI Control Dashboard</h1>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={toggleTheme}>
          {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </Button>
        <Button variant="ghost" size="icon" onClick={logout}>
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </header>
  );
}

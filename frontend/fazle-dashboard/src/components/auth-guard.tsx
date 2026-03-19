'use client';

import * as React from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/auth';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated, role, hydrate } = useAuthStore();
  const [checked, setChecked] = React.useState(false);

  React.useEffect(() => {
    hydrate();
    setChecked(true);
  }, [hydrate]);

  React.useEffect(() => {
    if (!checked) return;
    if (!isAuthenticated) {
      router.replace('/login');
    } else if (role !== 'admin') {
      router.replace('/');
    }
  }, [checked, isAuthenticated, role, router]);

  if (!checked || !isAuthenticated || role !== 'admin') {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}

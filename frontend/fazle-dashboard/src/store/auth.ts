import { create } from 'zustand';

interface AuthState {
  token: string | null;
  role: string | null;
  isAuthenticated: boolean;
  setAuth: (token: string, role: string) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  role: null,
  isAuthenticated: false,
  setAuth: (token, role) => {
    localStorage.setItem('fazle_token', token);
    localStorage.setItem('fazle_role', role);
    set({ token, role, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem('fazle_token');
    localStorage.removeItem('fazle_role');
    set({ token: null, role: null, isAuthenticated: false });
  },
  hydrate: () => {
    const token = localStorage.getItem('fazle_token');
    const role = localStorage.getItem('fazle_role');
    if (token) {
      set({ token, role, isAuthenticated: true });
    }
  },
}));

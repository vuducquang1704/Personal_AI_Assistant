import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (full_name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!token.get()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api<User>("/api/auth/me"));
    } catch {
      token.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email: string, password: string) => {
    const r = await api<{ access_token: string }>("/api/auth/login", { body: { email, password } });
    token.set(r.access_token);
    await refresh();
  };
  const register = async (full_name: string, email: string, password: string) => {
    const r = await api<{ access_token: string }>("/api/auth/register", { body: { full_name, email, password } });
    token.set(r.access_token);
    await refresh();
  };
  const logout = () => {
    token.clear();
    setUser(null);
  };

  return <Ctx.Provider value={{ user, loading, login, register, logout, refresh }}>{children}</Ctx.Provider>;
}

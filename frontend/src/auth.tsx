import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, tokenStore } from "./api";
import type { Me } from "./types";

interface AuthState {
  me: Me | undefined;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState(tokenStore.get());
  const meQuery = useQuery({
    queryKey: ["me", token],
    queryFn: () => api<Me>("/auth/me"),
    enabled: !!token,
    retry: false,
  });

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string }>("/auth/login", { method: "POST", json: { email, password } });
    tokenStore.set(res.access_token);
    setToken(res.access_token);
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    queryClient.clear();
  }, [queryClient]);

  const me = token && !meQuery.isError ? meQuery.data : undefined;
  return (
    <AuthContext.Provider value={{ me, loading: !!token && meQuery.isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider 안에서만 사용할 수 있습니다.");
  return ctx;
}

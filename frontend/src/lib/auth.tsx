import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

export type User = { id: number; email: string; role: string };
type AuthState = {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthCtx = createContext<AuthState | null>(null);
const KEY = "deplyx.auth";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "/api/v1";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem(KEY);
    if (raw) {
      try {
        const p = JSON.parse(raw);
        setUser(p.user);
        setToken(p.token);
        localStorage.setItem("deplyx_token", p.token);
      } catch {}
    }
  }, []);

  const persist = (u: User, t: string) => {
    setUser(u);
    setToken(t);
    localStorage.setItem(KEY, JSON.stringify({ user: u, token: t }));
    localStorage.setItem("deplyx_token", t);
  };

  const login = async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error("Login failed");
    const { access_token } = await res.json();
    const meRes = await fetch(`${BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    if (!meRes.ok) throw new Error("Failed to fetch user");
    const userData = await meRes.json();
    persist({ id: userData.id, email: userData.email, role: userData.role }, access_token);
  };

  const register = async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error("Registration failed");
    const { access_token } = await res.json();
    const meRes = await fetch(`${BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    if (!meRes.ok) throw new Error("Failed to fetch user");
    const userData = await meRes.json();
    persist({ id: userData.id, email: userData.email, role: userData.role }, access_token);
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem(KEY);
    localStorage.removeItem("deplyx_token");
    if (typeof window !== "undefined") window.location.href = "/login";
  };

  return (
    <AuthCtx.Provider value={{ user, token, isAuthenticated: !!token, login, register, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("AuthProvider missing");
  return v;
};

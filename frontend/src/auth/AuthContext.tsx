import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, refreshAccess, setAccessToken, setAuthLostHandler } from "../api/client";
import type { LoginOk, OtpRequired, SessionInfo, User } from "../api/types";

interface AuthState {
  status: "loading" | "anonymous" | "authenticated";
  user: User | null;
  session: SessionInfo | null;
  message: string | null;
  login: (username: string, password: string) => Promise<LoginOk | OtpRequired>;
  verifyOtp: (challengeId: string, code: string) => Promise<void>;
  resendOtp: (challengeId: string) => Promise<OtpRequired>;
  logout: () => Promise<void>;
  can: (perm: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reset = useCallback((msg: string | null) => {
    setAccessToken(null);
    setUser(null);
    setSession(null);
    setStatus("anonymous");
    setMessage(msg);
    qc.clear();
  }, [qc]);

  const accept = useCallback((data: LoginOk) => {
    setAccessToken(data.access_token);
    setUser(data.user);
    setSession(data.session);
    setMessage(null);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    setAuthLostHandler(() => reset("Your session has ended. Please sign in again."));
    (async () => {
      if (await refreshAccess()) {
        try {
          const { data } = await api.get("/auth/me");
          setUser(data.user);
          setSession(data.session);
          setStatus("authenticated");
          return;
        } catch { /* fall through */ }
      }
      setStatus("anonymous");
    })();
  }, [reset]);

  const value = useMemo<AuthState>(() => ({
    status, user, session, message,
    async login(username, password) {
      const { data } = await api.post<LoginOk | OtpRequired>("/auth/login", { username, password });
      if (data.status === "ok") accept(data);
      return data;
    },
    async verifyOtp(challengeId, code) {
      const { data } = await api.post<LoginOk>("/auth/otp/verify", { challenge_id: challengeId, code });
      accept(data);
    },
    async resendOtp(challengeId) {
      const { data } = await api.post<OtpRequired>("/auth/otp/resend", { challenge_id: challengeId });
      return data;
    },
    async logout() {
      try { await api.post("/auth/logout"); } finally { reset(null); }
    },
    can: (perm) => !!user?.permissions.includes(perm),
  }), [status, user, session, message, accept, reset]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

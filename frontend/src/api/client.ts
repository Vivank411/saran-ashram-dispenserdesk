import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

/** Access token lives in memory only; the refresh token is an HttpOnly cookie set by the API. */
let accessToken: string | null = null;
let onAuthLost: (() => void) | null = null;

export const setAccessToken = (token: string | null) => { accessToken = token; };
export const setAuthLostHandler = (fn: () => void) => { onAuthLost = fn; };

// The server identifies each hospital computer automatically (by its LAN IP), so no terminal setup is needed.
export const api = axios.create({ baseURL: "/api", withCredentials: true, timeout: 20000 });

api.interceptors.request.use((cfg) => {
  if (accessToken) cfg.headers.Authorization = `Bearer ${accessToken}`;
  return cfg;
});

let refreshing: Promise<string | null> | null = null;

export async function refreshAccess(): Promise<string | null> {
  try {
    const { data } = await axios.post("/api/auth/refresh", null, { withCredentials: true });
    setAccessToken(data.access_token);
    return data.access_token as string;
  } catch {
    setAccessToken(null);
    return null;
  }
}

api.interceptors.response.use(undefined, async (error: AxiosError<{ error?: { code?: string } }>) => {
  const cfg = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
  const code = error.response?.data?.error?.code;
  if (error.response?.status === 401 && cfg && !cfg._retried && !cfg.url?.startsWith("/auth/")) {
    if (code === "TOKEN_EXPIRED" || code === "AUTH") {
      cfg._retried = true;
      refreshing ??= refreshAccess().finally(() => { refreshing = null; });
      if (await refreshing) return api(cfg);
    }
    onAuthLost?.();
  }
  throw error;
});

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public extra: Record<string, unknown> = {}) {
    super(message);
  }
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (axios.isAxiosError(e)) {
    const err = (e.response?.data as { error?: { code: string; message: string } } | undefined)?.error;
    if (err) {
      const { code, message, ...extra } = err as { code: string; message: string } & Record<string, unknown>;
      return new ApiError(code, message, e.response!.status, extra);
    }
    if (!e.response) return new ApiError("NETWORK", "Cannot reach the server. Check the network connection.", 0);
    return new ApiError("HTTP_" + e.response.status, `Request failed (HTTP ${e.response.status}).`, e.response.status);
  }
  return new ApiError("UNKNOWN", (e as Error)?.message || "Unexpected error.", 0);
}

export const newRequestId = () =>
  crypto.randomUUID ? crypto.randomUUID() : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16));

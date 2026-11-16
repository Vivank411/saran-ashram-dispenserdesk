import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, toApiError } from "../api/client";
import type { SystemStatus } from "../api/types";
import { useToast } from "../components/Toasts";

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: async () => (await api.get<SystemStatus>("/system/status")).data,
    refetchInterval: 10_000,
  });
}

export function useGet<T>(key: unknown[], url: string, params?: Record<string, unknown>, opts: { enabled?: boolean; refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: [...key, params],
    queryFn: async () => (await api.get<T>(url, { params })).data,
    ...opts,
  });
}

/** POST/PUT/PATCH with toast on error and broad cache invalidation on success. */
export function useAction<TBody, TResult = unknown>(method: "post" | "put" | "patch", url: string | ((b: TBody) => string),
  onSuccess?: (data: TResult, body: TBody) => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: async (body: TBody) => (await api[method]<TResult>(typeof url === "function" ? url(body) : url, body)).data,
    onSuccess: (data, body) => {
      qc.invalidateQueries();
      onSuccess?.(data, body);
    },
    onError: (e) => toast(toApiError(e).message, "error"),
  });
}

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

type Kind = "ok" | "warn" | "error";
interface Toast { id: number; message: string; kind: Kind }
const ToastContext = createContext<(message: string, kind?: Kind) => void>(() => {});

const STYLE: Record<Kind, { icon: IconName; iconCls: string; bar: string }> = {
  ok: { icon: "checkCircle", iconCls: "text-good", bar: "bg-good" },
  warn: { icon: "alert", iconCls: "text-warn", bar: "bg-amber-500" },
  error: { icon: "alertCircle", iconCls: "text-danger", bar: "bg-danger" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));
  const push = useCallback((message: string, kind: Kind = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-4), { id, message, kind }]);
    setTimeout(() => dismiss(id), kind === "warn" ? 15000 : kind === "error" ? 8000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex w-[calc(100%-2.5rem)] max-w-sm flex-col gap-2.5" role="status" aria-live="polite">
        {toasts.map((t) => {
          const s = STYLE[t.kind];
          return (
            <div key={t.id} className="relative flex items-start gap-3 overflow-hidden rounded-xl border border-line bg-white py-3 pl-4 pr-3 text-[13px] text-ink shadow-pop">
              <span className={`absolute inset-y-0 left-0 w-1 ${s.bar}`} />
              <Icon name={s.icon} className={`mt-px h-[18px] w-[18px] ${s.iconCls}`} />
              <span className={`flex-1 ${t.kind === "warn" ? "font-semibold" : ""}`}>{t.message}</span>
              <button className="text-muted hover:text-ink" aria-label="Dismiss" onClick={() => dismiss(t.id)}><Icon name="x" className="h-4 w-4" /></button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

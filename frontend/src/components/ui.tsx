import { useEffect, type ReactNode } from "react";
import type { Source } from "../api/types";
import { fmtDateTime } from "../lib/format";
import { Icon, type IconName } from "./Icon";

type Tone = "accent" | "good" | "warn" | "danger" | "info" | "slate";
const TONE: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent", good: "bg-good-soft text-good", warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger", info: "bg-info-soft text-info", slate: "bg-slate-100 text-slate-600",
};

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
        {sub && <div className="mt-1 max-w-3xl text-[13.5px] text-muted">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, note, icon, tone = "accent" }:
  { label: string; value: ReactNode; note?: ReactNode; icon?: IconName; tone?: Tone }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-card sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[12.5px] font-medium text-muted">{label}</div>
        {icon && <span className={`grid h-8 w-8 place-items-center rounded-lg ${TONE[tone]}`}><Icon name={icon} /></span>}
      </div>
      <div className="mt-2 text-[26px] font-semibold leading-none tracking-tight text-ink tnum">{value}</div>
      {note && <div className="mt-2 text-xs text-muted">{note}</div>}
    </div>
  );
}

export function Panel({ title, sub, actions, children, className = "", flush = false, toolbar, clip = true }:
  { title?: string; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; flush?: boolean; toolbar?: ReactNode; clip?: boolean }) {
  return (
    <section className={`panel ${clip ? "overflow-hidden" : ""} ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {toolbar && <div className="flex flex-wrap items-center gap-2 border-b border-line bg-white px-5 py-3">{toolbar}</div>}
      <div className={flush ? "" : "panel-body"}>{children}</div>
    </section>
  );
}

export function Empty({ children, icon = "layers" }: { children: ReactNode; icon?: IconName }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center text-[13px] text-muted">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-slate-100 text-slate-400"><Icon name={icon} className="h-5 w-5" /></span>
      {children}
    </div>
  );
}

export function Table({ head, children, empty, colSpan, maxHeight }:
  { head: ReactNode; children: ReactNode; empty?: ReactNode; colSpan?: number; maxHeight?: string }) {
  const hasRows = Array.isArray(children) ? children.length > 0 : !!children;
  return (
    <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      <table className="tbl">
        <thead><tr>{head}</tr></thead>
        <tbody>{hasRows ? children : <tr className="hover:bg-transparent"><td colSpan={colSpan ?? 10}><Empty>{empty ?? "Nothing to show."}</Empty></td></tr>}</tbody>
      </table>
    </div>
  );
}

export function Modal({ title, sub, children, onClose, footer, wide = false }:
  { title: string; sub?: ReactNode; children: ReactNode; onClose: () => void; footer: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 grid place-items-center overflow-auto bg-slate-900/40 p-4 backdrop-blur-[2px]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`w-full ${wide ? "max-w-2xl" : "max-w-lg"} overflow-hidden rounded-2xl bg-white shadow-pop`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-start justify-between gap-4 px-6 pb-2 pt-5">
          <div>
            <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
            {sub && <p className="mt-1 text-[13px] text-muted">{sub}</p>}
          </div>
          <button className="btn btn-ghost btn-sm -mr-2 px-1.5 text-muted" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="px-6 py-4">{children}</div>
        <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-slate-50/80 px-6 py-3.5">{footer}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, className = "", hint }: { label: string; children: ReactNode; className?: string; hint?: ReactNode }) {
  return (
    <label className={`flex flex-col gap-1.5 ${className}`}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="text-[11.5px] text-muted">{hint}</span>}
    </label>
  );
}

export function SearchInput({ value, onChange, placeholder, className = "max-w-sm", autoFocus }:
  { value: string; onChange: (v: string) => void; placeholder: string; className?: string; autoFocus?: boolean }) {
  return (
    <div className={`relative w-full ${className}`}>
      <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input className="input pl-9" value={value} placeholder={placeholder} autoFocus={autoFocus} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function SourceBadge({ source, lastSync }: { source?: Source; lastSync?: string | null }) {
  if (!source) return null;
  if (source === "cloud_replica")
    return <span className="pill pill-warn"><Icon name="cloud" className="h-3.5 w-3.5" />Cloud copy · as of {fmtDateTime(lastSync)}</span>;
  return <span className="pill pill-accent"><Icon name="server" className="h-3.5 w-3.5" />{source === "hospital_live" ? "Live from hospital server" : "Live"}</span>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "error"; children: ReactNode }) {
  const cls = { info: "border-accent-ring/50 bg-accent-soft text-accent-dark", warn: "border-warn-line bg-warn-soft text-warn", error: "border-danger-line bg-danger-soft text-danger" }[tone];
  const icon: IconName = tone === "info" ? "info" : tone === "warn" ? "alert" : "alertCircle";
  return <div className={`notice ${cls}`}><Icon name={icon} className="mt-px h-4 w-4" /><div className="min-w-0">{children}</div></div>;
}

export function Dot({ tone }: { tone: "good" | "warn" | "bad" | "slate" }) {
  const c = { good: "bg-good", warn: "bg-amber-500", bad: "bg-danger", slate: "bg-slate-400" }[tone];
  return <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${c}`} />;
}

export function StockPill({ stock, threshold }: { stock: number; threshold: number }) {
  if (stock < 0) return <span className="pill pill-bad"><Dot tone="bad" />Negative</span>;
  if (stock === 0) return <span className="pill pill-bad"><Dot tone="bad" />Out of stock</span>;
  if (stock <= threshold) return <span className="pill pill-warn"><Dot tone="warn" />Low stock</span>;
  return <span className="pill"><Dot tone="good" />In stock</span>;
}

export function Tabs<T extends string>({ value, onChange, tabs }: { value: T; onChange: (v: T) => void; tabs: [T, string][] }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-slate-100/70 p-0.5">
      {tabs.map(([key, label]) => (
        <button key={key} onClick={() => onChange(key)}
          className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition ${value === key ? "bg-white text-ink shadow-card" : "text-muted hover:text-ink"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Avatar({ name, size = "h-8 w-8" }: { name?: string; size?: string }) {
  const initials = (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return <span className={`grid ${size} shrink-0 place-items-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent-dark ring-1 ring-accent-ring/50`}>{initials}</span>;
}

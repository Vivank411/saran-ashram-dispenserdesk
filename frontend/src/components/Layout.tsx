import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import type { Dashboard } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ago, fmtDateTime, fmtTime } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";
import { Icon, type IconName } from "./Icon";
import { Avatar } from "./ui";

interface NavItem { to: string; label: string; icon: IconName; perms?: string[]; badge?: "alerts" | "sync" | "approvals" }
export const NAV: { section: string; items: NavItem[] }[] = [
  { section: "Workspace", items: [
    { to: "/", label: "Dashboard", icon: "dashboard" },
    { to: "/bills/new", label: "New bill", icon: "billNew", perms: ["bill.create"] },
    { to: "/bills", label: "Bill history", icon: "bills", perms: ["bill.view"] },
    { to: "/stock", label: "Stock & ledger", icon: "stock", perms: ["stock.view"] },
    { to: "/approvals", label: "Approvals", icon: "approvals", perms: ["stock.request", "stock.approve"], badge: "approvals" },
    { to: "/alerts", label: "Low-stock alerts", icon: "bell", perms: ["stock.view"], badge: "alerts" },
  ] },
  { section: "Insights", items: [
    { to: "/reports", label: "Reports", icon: "reports", perms: ["reports.view"] },
    { to: "/sync", label: "Sync monitor", icon: "sync", perms: ["sync.view"], badge: "sync" },
    { to: "/audit", label: "Audit log", icon: "audit", perms: ["audit.view"] },
  ] },
  { section: "Administration", items: [
    { to: "/users", label: "Users & access", icon: "users", perms: ["users.manage"] },
    { to: "/settings", label: "Settings", icon: "settings", perms: ["settings.manage"] },
  ] },
];
const ALL_ITEMS = NAV.flatMap((s) => s.items);

function Banner({ tone, icon, children }: { tone: "warn" | "danger"; icon: IconName; children: ReactNode }) {
  const cls = tone === "warn" ? "border-warn-line bg-warn-soft text-warn" : "border-danger-line bg-danger-soft text-danger";
  return <div className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3 text-[13px] ${cls}`}><Icon name={icon} className="mt-0.5 h-4 w-4" /><div>{children}</div></div>;
}

export default function Layout() {
  const { user, session, can, logout } = useAuth();
  const { data: status } = useStatus();
  const { data: dash } = useGet<Dashboard>(["dashboard"], "/dashboard", undefined, { refetchInterval: 30_000 });
  const pendingApprovals = useGet<{ items: unknown[] }>(["adjustments", "pending-count"], "/adjustments", { status: "pending" },
    { enabled: can("stock.approve"), refetchInterval: 30_000 });
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const [now, setNow] = useState(new Date());
  const menuRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => { setOpen(false); setMenu(false); }, [location.pathname]);
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => {
    const close = (e: MouseEvent) => menuRef.current && !menuRef.current.contains(e.target as Node) && setMenu(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const isCloud = status?.role === "cloud";
  const standalone = !!status?.standalone; // single server: no sync to show
  const live = status?.live_operations ?? true;
  const conflicts = status?.conflicts ?? 0;
  const queued = (status?.pending ?? 0) + (status?.failed ?? 0);
  const badges = { alerts: dash?.active_alerts ?? 0, sync: conflicts + (status?.failed ?? 0), approvals: pendingApprovals.data?.items.length ?? 0 };
  const current = ALL_ITEMS.find((i) => i.to === location.pathname) ?? ALL_ITEMS.find((i) => i.to !== "/" && location.pathname.startsWith(i.to));

  const conn = conflicts ? { tone: "bad", icon: "alertCircle" as IconName, text: `${conflicts} sync conflict${conflicts > 1 ? "s" : ""}` }
    : isCloud ? (live ? { tone: "good", icon: "server" as IconName, text: "Hospital server online" } : { tone: "bad", icon: "cloudOff" as IconName, text: "Hospital server unreachable" })
    : status?.cloud_reachable ? (queued ? { tone: "warn", icon: "sync" as IconName, text: `Syncing · ${queued} pending` } : { tone: "good", icon: "cloud" as IconName, text: "Cloud in sync" })
    : { tone: "warn", icon: "cloudOff" as IconName, text: `Offline · ${queued} queued` };
  const connCls = { good: "border-good-line bg-good-soft text-good", warn: "border-warn-line bg-warn-soft text-warn", bad: "border-danger-line bg-danger-soft text-danger" }[conn.tone];

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_1fr]">
      {open && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`${open ? "translate-x-0" : "-translate-x-full"} fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy text-slate-300 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0`}>
        <div className="flex items-center gap-3 px-5 pb-5 pt-5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-teal-400 to-teal-600 text-white shadow-lg shadow-teal-900/40">
            <Icon name="pill" className="h-[18px] w-[18px]" strokeWidth={2} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-white" title={status?.hospital_name}>{status?.hospital_name ?? "Dispensary Desk"}</div>
            <div className="text-[11px] text-slate-400">{isCloud ? "Remote access" : "Hospital terminal"}</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {NAV.map((sec) => {
            const items = sec.items.filter((i) => (!i.perms || i.perms.some(can)) && !(standalone && i.to === "/sync"));
            if (!items.length) return null;
            return (
              <div key={sec.section} className="mb-5">
                <div className="mb-1.5 px-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-slate-500">{sec.section}</div>
                {items.map((i) => (
                  <NavLink key={i.to} to={i.to} end={i.to === "/" || i.to === "/bills"}
                    className={({ isActive }) => `group relative my-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors ${isActive ? "bg-white/[0.08] text-white" : "text-slate-300 hover:bg-white/[0.05] hover:text-white"}`}>
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-teal-400" />}
                        <Icon name={i.icon} className={`h-[18px] w-[18px] ${isActive ? "text-teal-300" : "text-slate-400 group-hover:text-slate-200"}`} />
                        {i.label}
                        {i.badge && badges[i.badge] > 0 && (
                          <span className={`ml-auto min-w-[20px] rounded-full px-1.5 text-center text-[10.5px] font-bold leading-5 text-white ${i.badge === "sync" ? "bg-red-500" : "bg-amber-500"}`}>{badges[i.badge]}</span>
                        )}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        {!standalone && (
          <div className="m-3 rounded-xl bg-white/[0.05] p-3 ring-1 ring-white/10">
            <div className="flex items-center gap-2 text-[12px] font-medium text-slate-200">
              <span className={`h-2 w-2 rounded-full ${conn.tone === "good" ? "bg-emerald-400" : conn.tone === "warn" ? "bg-amber-400" : "bg-red-400"}`} />{conn.text}
            </div>
            <div className="mt-1 text-[11px] text-slate-400">Last sync {ago(status?.last_sync)}</div>
          </div>
        )}
      </aside>

      <main className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-line bg-white/90 px-4 backdrop-blur md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button className="btn btn-ghost btn-sm px-1.5 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Icon name="menu" className="h-5 w-5" /></button>
            <nav className="flex min-w-0 items-center gap-1.5 text-[13px] text-muted" aria-label="Breadcrumb">
              <Link to="/" className="hidden hover:text-ink sm:inline">Dispensary</Link>
              <Icon name="chevronRight" className="hidden h-3.5 w-3.5 text-slate-300 sm:block" />
              <span className="truncate font-semibold text-ink">{current?.label ?? "Dashboard"}</span>
            </nav>
          </div>
          <div className="flex items-center gap-2 sm:gap-4">
            {!standalone && (
              <span className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-semibold md:inline-flex ${connCls}`}>
                <Icon name={conn.icon} className="h-3.5 w-3.5" />{conn.text}
              </span>
            )}
            <div className="hidden text-right leading-tight xl:block">
              <div className="text-[13px] font-semibold text-ink tnum">{now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</div>
              <div className="text-[11px] text-muted">{now.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })}</div>
            </div>
            <div className="relative" ref={menuRef}>
              <button className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 hover:bg-slate-100" onClick={() => setMenu(!menu)} aria-haspopup="menu" aria-expanded={menu}>
                <Avatar name={user?.full_name} />
                <span className="hidden text-left leading-tight sm:block">
                  <span className="block text-[13px] font-semibold text-ink">{user?.full_name}</span>
                  <span className="block text-[11px] text-muted">{user?.role}</span>
                </span>
                <Icon name="chevronDown" className="h-4 w-4 text-muted" />
              </button>
              {menu && (
                <div className="absolute right-0 top-12 z-30 w-64 overflow-hidden rounded-xl border border-line bg-white shadow-pop" role="menu">
                  <div className="border-b border-line px-4 py-3">
                    <div className="text-[13px] font-semibold text-ink">{user?.full_name}</div>
                    <div className="text-xs text-muted">@{user?.username} · {user?.role}</div>
                  </div>
                  <dl className="space-y-1.5 px-4 py-3 text-xs">
                    <div className="flex justify-between gap-3"><dt className="text-muted">Signed in from</dt><dd className="font-medium text-ink-soft">{session?.channel === "remote" ? "Remote access" : session?.terminal}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-muted">Session ends</dt><dd className="font-medium text-ink-soft">{session && fmtTime(session.expires_at)}</dd></div>
                    {session?.offline && <div className="flex justify-between gap-3"><dt className="text-muted">Mode</dt><dd className="font-medium text-warn">Offline sign-in</dd></div>}
                  </dl>
                  <button className="flex w-full items-center gap-2 border-t border-line px-4 py-2.5 text-left text-[13px] font-medium text-danger hover:bg-danger-soft" onClick={logout} role="menuitem">
                    <Icon name="logout" />Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-[1440px] px-4 py-6 md:px-8 md:py-8">
          {isCloud && !live && (
            <Banner tone="danger" icon="cloudOff"><b>Live billing is temporarily unavailable.</b> The hospital server cannot be reached. You are viewing
              read-only data last synchronized <b>{fmtDateTime(status?.last_sync)}</b> ({ago(status?.last_sync)}).</Banner>
          )}
          {!isCloud && status && !status.cloud_reachable && (
            <Banner tone="warn" icon="cloudOff"><b>Working offline.</b> The internet is unavailable, but billing, stock, alerts and reports continue normally.
              {queued > 0 && <> {queued} change{queued > 1 ? "s" : ""} will synchronize automatically when the connection returns.</>}</Banner>
          )}
          {conflicts > 0 && can("sync.view") && (
            <Banner tone="danger" icon="alertCircle"><b>{conflicts} synchronization conflict{conflicts > 1 ? "s" : ""} need review.</b> Synchronization is paused and nothing
              was overwritten. <Link className="font-semibold underline" to="/sync">Open sync monitor</Link></Banner>
          )}
          <Outlet />
        </div>
      </main>
    </div>
  );
}

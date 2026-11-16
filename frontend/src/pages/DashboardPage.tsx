import { Link } from "react-router-dom";
import type { Dashboard } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "../components/Icon";
import { Empty, PageHeader, Panel, SourceBadge, Stat, Table } from "../components/ui";
import { ago, fmtDateTime, fmtTime, money } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";

export default function DashboardPage() {
  const { user, can } = useAuth();
  const { data: status } = useStatus();
  const { data: d } = useGet<Dashboard>(["dashboard"], "/dashboard", undefined, { refetchInterval: 15_000 });
  const hour = new Date().getHours();
  const live = status?.live_operations ?? true;
  const isCloud = status?.role === "cloud";
  const top = d?.top_medicines ?? [];
  const maxQty = Math.max(1, ...top.map((m) => m.qty));

  const sync: { tone: string; icon: IconName; title: string; text: string } =
    status?.conflicts ? { tone: "bg-danger-soft text-danger", icon: "alertCircle", title: "Needs review", text: `${status.conflicts} conflict(s) — synchronization paused` }
      : isCloud ? (live ? { tone: "bg-good-soft text-good", icon: "server", title: "Hospital server online", text: "Live operations available" }
        : { tone: "bg-danger-soft text-danger", icon: "cloudOff", title: "Hospital unreachable", text: "Showing last synchronized data" })
      : status?.standalone ? { tone: "bg-good-soft text-good", icon: "server", title: "Standalone server", text: "All data is stored on this server" }
      : status?.cloud_reachable ? { tone: "bg-good-soft text-good", icon: "cloud", title: "Cloud in sync", text: "All changes backed up to the cloud" }
        : { tone: "bg-warn-soft text-warn", icon: "cloudOff", title: "Working offline", text: "Changes are queued and will sync automatically" };

  return (
    <>
      <PageHeader
        title={`Good ${hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"}, ${user?.full_name.split(" ")[0]}`}
        sub={<span className="inline-flex flex-wrap items-center gap-2">
          {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          <SourceBadge source={d?.source} lastSync={status?.last_sync} /></span>}
        actions={<>
          {can("stock.view") && <Link className="btn" to="/stock"><Icon name="stock" />Stock</Link>}
          {can("bill.create") && live && <Link className="btn btn-primary" to="/bills/new"><Icon name="plus" />New bill</Link>}
        </>}
      />

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Stat label="Today's sales" value={money(d?.sales)} icon="rupee" tone="accent" note="Net of reversed bills" />
        <Stat label="Bills today" value={d?.bills ?? "—"} icon="bills" tone="info" note="Patients served" />
        <Stat label="Units dispensed" value={d?.units ?? "—"} icon="pill" tone="slate" note="Across all bills today" />
        <Stat label="Low-stock items" value={d?.low_stock ?? "—"} icon="alert" tone="warn"
          note={<><span className="tnum">{d?.out_of_stock ?? 0}</span> out of stock · threshold {d?.threshold ?? 50}</>} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <Panel title="Dispensed today" sub="Top medicines by units issued"
            actions={can("reports.view") && <Link className="btn btn-sm" to="/reports">Full report<Icon name="arrowRight" className="h-3.5 w-3.5" /></Link>}>
            {top.length ? (
              <ul className="space-y-3.5" aria-label="Units dispensed per medicine today">
                {top.map((m) => (
                  <li key={m.medicine_id} className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 sm:grid-cols-[minmax(0,180px)_1fr_auto]"
                    title={`${m.medicine_name}: ${m.qty} units · ${money(m.amount)}`}>
                    <span className="truncate text-[13px] font-medium text-ink-soft">{m.medicine_name}</span>
                    <span className="order-last col-span-2 h-2 rounded-full bg-slate-100 sm:order-none sm:col-span-1">
                      <span className="block h-2 rounded-full bg-accent transition-all group-hover:bg-accent-dark" style={{ width: `${(m.qty / maxQty) * 100}%` }} />
                    </span>
                    <span className="text-right text-[13px] tnum sm:w-24"><b className="text-ink">{m.qty}</b> <span className="text-muted">units</span></span>
                  </li>
                ))}
              </ul>
            ) : <Empty icon="pill">No medicine has been dispensed today yet.</Empty>}
          </Panel>

          <Panel title="Recent bills" sub="Latest customer transactions today" flush
            actions={can("bill.view") && <Link className="btn btn-sm" to="/bills">View all<Icon name="arrowRight" className="h-3.5 w-3.5" /></Link>}>
            <Table colSpan={5} empty="No bills created today."
              head={<><th>Bill</th><th>Customer</th><th>Time</th><th>Counter</th><th className="num">Amount</th></>}>
              {d?.recent_bills.map((b) => (
                <tr key={b.id}>
                  <td><span className="font-semibold text-ink">{b.bill_no}</span>
                    {b.status === "reversed" && <span className="pill pill-bad ml-2">Reversed</span>}
                    {b.created_offline && <span className="pill pill-grey ml-2">Offline</span>}</td>
                  <td>{b.customer_name || <span className="text-muted">Walk-in</span>}</td>
                  <td>{fmtTime(b.created_at)}</td>
                  <td>{b.terminal}</td>
                  <td className="num font-semibold text-ink">{money(b.total)}</td>
                </tr>
              ))}
            </Table>
          </Panel>
        </div>

        <div className="min-w-0">
          <Panel title="Synchronization" actions={can("sync.view") && <Link className="btn btn-sm" to="/sync">Details</Link>}>
            <div className="flex items-center gap-3">
              <span className={`grid h-11 w-11 place-items-center rounded-xl ${sync.tone}`}><Icon name={sync.icon} className="h-5 w-5" /></span>
              <div><div className="font-semibold text-ink">{sync.title}</div><div className="text-xs text-muted">{sync.text}</div></div>
            </div>
            <dl className="mt-4 grid grid-cols-3 divide-x divide-line rounded-lg border border-line text-center">
              {[["Pending", status?.pending], ["Failed", status?.failed], ["Conflicts", status?.conflicts]].map(([k, v]) => (
                <div key={k as string} className="px-2 py-2.5"><dt className="text-[11px] text-muted">{k}</dt><dd className="text-[17px] font-semibold text-ink tnum">{v ?? "—"}</dd></div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-muted">Last successful sync: <span className="font-medium text-ink-soft">{fmtDateTime(status?.last_sync)}</span> ({ago(status?.last_sync)})</p>
          </Panel>

          <Panel title="Low-stock alerts" sub={`${d?.active_alerts ?? 0} active · at or below ${d?.threshold ?? 50} units`}
            actions={<Link className="btn btn-sm" to="/alerts">View all</Link>} flush>
            {d?.alerts.length ? (
              <ul className="divide-y divide-line">
                {d.alerts.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 px-5 py-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-warn-soft text-warn"><Icon name="alert" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-semibold text-ink">{a.medicine_name}</div>
                      <div className="text-xs text-muted">{ago(a.updated_at)}</div>
                    </div>
                    <span className="pill pill-warn tnum">{a.remaining} left</span>
                  </li>
                ))}
              </ul>
            ) : <Empty icon="checkCircle">No active low-stock alerts.</Empty>}
          </Panel>
        </div>
      </div>
    </>
  );
}

import type { Listing, StockAlert } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Empty, PageHeader, Panel, SourceBadge, Table } from "../components/ui";
import { ago, fmtDateTime } from "../lib/format";
import { useAction, useGet, useStatus } from "../lib/hooks";

export default function AlertsPage() {
  const { can } = useAuth();
  const { data: status } = useStatus();
  const toast = useToast();
  const active = useGet<Listing<StockAlert>>(["alerts", "active"], "/alerts", { active: true }, { refetchInterval: 15_000 });
  const done = useGet<Listing<StockAlert>>(["alerts", "done"], "/alerts", { active: false, limit: 100 });
  const ack = useAction<{ id: string }>("post", (b) => `/alerts/${b.id}/ack`, () => toast("Alert acknowledged"));
  const canAck = can("alerts.ack") && (status?.live_operations ?? true);
  const list = active.data?.items ?? [];
  return (
    <>
      <PageHeader title="Low-stock alerts"
        sub={`Raised the moment a bill or approved change takes a medicine to ${status?.low_stock_threshold ?? 50} units or fewer — even without internet.`}
        actions={<SourceBadge source={active.data?.source} lastSync={status?.last_sync} />} />
      <Panel title="Active alerts" sub={`${list.length} medicine${list.length === 1 ? "" : "s"} need restocking`} flush>
        {list.length ? (
          <ul className="divide-y divide-line">
            {list.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-warn-soft text-warn"><Icon name="alert" className="h-5 w-5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-ink">{a.message}</div>
                  <div className="mt-0.5 text-xs text-muted">Raised {fmtDateTime(a.raised_at)} · updated {ago(a.updated_at)}</div>
                </div>
                <span className="pill pill-warn tnum">{a.remaining} / {a.threshold} units</span>
                {canAck && <button className="btn btn-sm" disabled={ack.isPending} onClick={() => ack.mutate({ id: a.id })}><Icon name="check" className="h-3.5 w-3.5" />Acknowledge</button>}
              </li>
            ))}
          </ul>
        ) : <Empty icon="checkCircle">All medicines are above the low-stock threshold.</Empty>}
      </Panel>
      <Panel title="Acknowledged" sub="Most recent 100" flush>
        <Table colSpan={4} empty="No acknowledged alerts yet." head={<><th>Alert</th><th>Raised</th><th>Acknowledged</th><th>By</th></>}>
          {done.data?.items.map((a) => (
            <tr key={a.id}><td className="text-ink">{a.message}</td><td>{fmtDateTime(a.raised_at)}</td><td>{fmtDateTime(a.acknowledged_at)}</td><td>{a.acknowledged_by}</td></tr>
          ))}
        </Table>
      </Panel>
    </>
  );
}

import { useState } from "react";
import type { Adjustment, Listing, Medicine } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import AdjustmentModal from "../components/AdjustmentModal";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Dot, Field, Modal, PageHeader, Panel, SourceBadge, Table, Tabs } from "../components/ui";
import { fmtDateTime, KIND_LABELS, money } from "../lib/format";
import { useAction, useGet, useStatus } from "../lib/hooks";

function describe(a: Adjustment) {
  if (a.kind === "add") return `+${a.quantity} units`;
  if (a.kind === "remove") return `−${a.quantity} units`;
  if (a.kind === "set_count") return `Count → ${a.quantity}`;
  return `${money(a.rate_at_request)} → ${money(a.new_rate)}`;
}

function StatusBadge({ a }: { a: Adjustment }) {
  if (a.status === "pending") return <span className="pill pill-warn"><Dot tone="warn" />Pending</span>;
  if (a.status === "approved") return <span className="pill"><Dot tone="good" />{a.decision_note === "Applied directly by Admin" ? "Applied" : "Approved"}</span>;
  return <span className="pill pill-bad"><Dot tone="bad" />Rejected</span>;
}

export default function ApprovalsPage() {
  const { can, user } = useAuth();
  const { data: status } = useStatus();
  const toast = useToast();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [deciding, setDeciding] = useState<{ a: Adjustment; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const [creating, setCreating] = useState(false);
  const { data } = useGet<Listing<Adjustment>>(["adjustments"], "/adjustments");
  const meds = useGet<Listing<Medicine>>(["medicines"], "/medicines", undefined, { enabled: creating });
  const decide = useAction<{ id: string; approve: boolean; note: string }, { adjustment: Adjustment; alerts: string[] }>(
    "post", (b) => `/adjustments/${b.id}/decide`, (r) => {
      toast(`${r.adjustment.request_no} ${r.adjustment.status}`);
      r.alerts.forEach((m) => toast(m, "warn"));
      setDeciding(null);
      setNote("");
    });
  const live = status?.live_operations ?? true;
  const isAdmin = can("stock.approve");
  const all = data?.items ?? [];
  const pending = all.filter((a) => a.status === "pending");
  const items = tab === "pending" ? pending : all.filter((a) => a.status !== "pending");

  return (
    <>
      <PageHeader title="Approvals"
        sub={isAdmin ? "Stock and rate changes requested by billers wait here for your decision. Your own changes apply immediately."
          : "Stock and rate changes you request are applied after the Admin approves them."}
        actions={<><SourceBadge source={data?.source} lastSync={status?.last_sync} />
          {can("stock.request") && live && <button className="btn btn-primary" onClick={() => setCreating(true)}><Icon name="plus" />{isAdmin ? "Adjust stock" : "New request"}</button>}</>} />
      <Panel flush toolbar={<>
        <Tabs value={tab} onChange={setTab} tabs={[["pending", `Pending · ${pending.length}`], ["history", "History"]]} />
        {isAdmin && pending.length > 0 && tab === "pending" && <span className="ml-auto text-[13px] text-muted">{pending.length} request{pending.length > 1 ? "s" : ""} need your decision</span>}
      </>}>
        <Table colSpan={7} empty={tab === "pending" ? "Nothing is waiting for approval." : "No decided requests yet."}
          head={<><th>Request</th><th>Medicine</th><th>Change</th><th>Reason</th><th>Requested by</th><th>Status</th><th /></>}>
          {items.map((a) => (
            <tr key={a.id}>
              <td><div className="font-semibold text-ink">{a.request_no}</div><div className="text-xs text-muted">{fmtDateTime(a.requested_at)}</div></td>
              <td><div className="font-medium text-ink">{a.medicine_name}</div><div className="text-xs text-muted">Stock then: {a.stock_at_request}</div></td>
              <td><div className="font-semibold text-ink tnum">{describe(a)}</div><div className="text-xs text-muted">{KIND_LABELS[a.kind]}</div></td>
              <td className="max-w-[260px] whitespace-normal">{a.reason}</td>
              <td>{a.requested_by_name}<div className="text-xs text-muted">{a.channel === "remote" ? "Remote" : "Hospital"}</div></td>
              <td><StatusBadge a={a} />{a.decided_by_name && a.status !== "pending" && <div className="mt-1 text-xs text-muted">{a.decided_by_name} · {fmtDateTime(a.decided_at)}</div>}</td>
              <td>
                {a.status === "pending" && (isAdmin && live
                  ? <div className="flex justify-end gap-1.5">
                      <button className="btn btn-sm btn-primary" onClick={() => setDeciding({ a, approve: true })}><Icon name="check" className="h-3.5 w-3.5" />Approve</button>
                      <button className="btn btn-sm btn-danger" onClick={() => setDeciding({ a, approve: false })}><Icon name="x" className="h-3.5 w-3.5" />Reject</button>
                    </div>
                  : <span className="text-xs text-muted">{a.requested_by_id === user?.id ? "Waiting for Admin" : "Awaiting Admin"}</span>)}
              </td>
            </tr>
          ))}
        </Table>
      </Panel>
      {deciding && (
        <Modal title={`${deciding.approve ? "Approve" : "Reject"} ${deciding.a.request_no}`} onClose={() => setDeciding(null)}
          sub={deciding.approve ? "The change is applied to stock immediately and recorded in the ledger." : "Stock stays unchanged. The biller can see your note."}
          footer={<><button className="btn" onClick={() => setDeciding(null)}>Cancel</button>
            <button className={`btn ${deciding.approve ? "btn-primary" : "btn-danger"}`} disabled={decide.isPending || (!deciding.approve && note.trim().length < 3)}
              onClick={() => decide.mutate({ id: deciding.a.id, approve: deciding.approve, note })}>{deciding.approve ? "Approve & apply" : "Reject request"}</button></>}>
          <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-lg border border-line bg-slate-50 px-4 py-3 text-[13px]">
            <dt className="text-muted">Medicine</dt><dd className="font-semibold text-ink">{deciding.a.medicine_name}</dd>
            <dt className="text-muted">Change</dt><dd className="font-semibold text-ink">{describe(deciding.a)}</dd>
            <dt className="text-muted">Requested by</dt><dd className="text-ink-soft">{deciding.a.requested_by_name}</dd>
            <dt className="text-muted">Reason</dt><dd className="text-ink-soft">{deciding.a.reason}</dd>
          </dl>
          <Field label={deciding.approve ? "Note (optional)" : "Reason for rejection"}><input className="input" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} /></Field>
        </Modal>
      )}
      {creating && meds.data && <AdjustmentModal medicines={meds.data.items} initialId={null} onClose={() => setCreating(false)} />}
    </>
  );
}

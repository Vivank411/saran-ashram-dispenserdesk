import { useState } from "react";
import type { Bill, Listing } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Dot, Field, Modal, PageHeader, Panel, SearchInput, SourceBadge, Table } from "../components/ui";
import { fmtDate, fmtTime, money } from "../lib/format";
import { useAction, useGet, useStatus } from "../lib/hooks";
import { printReceipt } from "../lib/receipt";

export default function BillsPage() {
  const { can } = useAuth();
  const { data: status } = useStatus();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [reversing, setReversing] = useState<Bill | null>(null);
  const [reason, setReason] = useState("");
  const { data } = useGet<Listing<Bill>>(["bills"], "/bills", { q, limit: 200 });
  const reverse = useAction<{ id: string; reason: string }, Bill>("post", (b) => `/bills/${b.id}/reverse`, (bill) => {
    toast(`${bill.bill_no} reversed · stock restored via ${bill.reversal_ref}`);
    setReversing(null);
    setReason("");
  });
  const canReverse = can("bill.reverse") && (status?.live_operations ?? true);
  const hospital = status?.hospital_name ?? "Hospital Dispensary";
  const items = data?.items ?? [];

  return (
    <>
      <PageHeader title="Bill history" sub="Every customer transaction, with receipt reprints and audited reversals."
        actions={<SourceBadge source={data?.source} lastSync={status?.last_sync} />} />
      <Panel flush toolbar={<>
        <SearchInput value={q} onChange={setQ} placeholder="Search bill no., customer, patient ID, operator or counter" className="max-w-md" />
        <span className="ml-auto text-[13px] text-muted tnum">{items.length} bill{items.length === 1 ? "" : "s"}</span>
      </>}>
        <Table colSpan={9} empty="No bills recorded yet." maxHeight="calc(100vh - 260px)"
          head={<><th>Bill</th><th>Date</th><th>Customer</th><th className="num">Items</th><th>Operator</th><th>Counter</th><th>Status</th><th className="num">Amount</th><th /></>}>
          {items.map((b) => (
            <tr key={b.id}>
              <td><div className="font-semibold text-ink">{b.bill_no}</div><div className="text-xs text-muted">{b.payment_mode}{b.created_offline ? " · created offline" : ""}</div></td>
              <td>{fmtDate(b.business_date)}<div className="text-xs text-muted">{fmtTime(b.created_at)}</div></td>
              <td>{b.customer_name || <span className="text-muted">Walk-in</span>}{b.patient_ref && <div className="text-xs text-muted">ID {b.patient_ref}</div>}</td>
              <td className="num">{b.items.length}<div className="text-xs text-muted">{b.items.reduce((a, i) => a + i.qty, 0)} units</div></td>
              <td>{b.operator_name}</td>
              <td>{b.terminal}</td>
              <td>{b.status === "reversed"
                ? <span className="pill pill-bad" title={`${b.reversal_ref} · ${b.reversal_reason}`}><Dot tone="bad" />Reversed</span>
                : <span className="pill"><Dot tone="good" />Confirmed</span>}</td>
              <td className="num font-semibold text-ink">{money(b.total)}</td>
              <td>
                <div className="flex justify-end gap-1.5">
                  <button className="btn btn-sm" onClick={() => printReceipt(b, hospital) || toast("Allow pop-ups to print.", "error")}><Icon name="printer" className="h-3.5 w-3.5" />Print</button>
                  {canReverse && b.status === "confirmed" && <button className="btn btn-sm btn-danger" onClick={() => setReversing(b)}><Icon name="undo" className="h-3.5 w-3.5" />Reverse</button>}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      </Panel>
      {reversing && (
        <Modal title={`Reverse ${reversing.bill_no}`} onClose={() => setReversing(null)}
          sub="All items go back into stock through a separate, audited reversal entry. The original bill is kept and marked as reversed."
          footer={<><button className="btn" onClick={() => setReversing(null)}>Cancel</button>
            <button className="btn btn-danger" disabled={reason.trim().length < 3 || reverse.isPending}
              onClick={() => reverse.mutate({ id: reversing.id, reason: reason.trim() })}><Icon name="undo" />Confirm reversal</button></>}>
          <div className="mb-4 flex items-center justify-between rounded-lg border border-line bg-slate-50 px-4 py-3 text-[13px]">
            <span className="text-muted">{reversing.items.length} item(s) · {reversing.customer_name || "Walk-in"}</span>
            <b className="text-ink tnum">{money(reversing.total)}</b>
          </div>
          <Field label="Reason for reversal"><input className="input" autoFocus value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Wrong patient, returned unopened" /></Field>
        </Modal>
      )}
    </>
  );
}

import { useState } from "react";
import type { Adjustment, Medicine } from "../api/types";
import { KIND_LABELS, money } from "../lib/format";
import { useAction } from "../lib/hooks";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "./Toasts";
import { Field, Modal } from "./ui";

type Kind = Adjustment["kind"];

export default function AdjustmentModal({ medicines, initialId, onClose }: { medicines: Medicine[]; initialId: number | null; onClose: () => void }) {
  const toast = useToast();
  const { can } = useAuth();
  const isAdmin = can("stock.approve");
  const [medicineId, setMedicineId] = useState<number>(initialId ?? medicines[0]?.id);
  const [kind, setKind] = useState<Kind>("add");
  const [quantity, setQuantity] = useState("1");
  const [rate, setRate] = useState("");
  const [reason, setReason] = useState("");
  const submit = useAction<object, Adjustment & { alerts?: string[] }>("post", "/adjustments", (a) => {
    toast(a.status === "approved" ? `${a.request_no} applied to stock` : `${a.request_no} sent to Admin for approval`);
    a.alerts?.forEach((m) => toast(m, "warn"));
    onClose();
  });

  function send() {
    submit.mutate(kind === "set_rate"
      ? { medicine_id: medicineId, kind, new_rate: rate, reason }
      : { medicine_id: medicineId, kind, quantity: Number(quantity), reason });
  }

  return (
    <Modal title={isAdmin ? "Stock adjustment" : "Stock adjustment request"} onClose={onClose}
      sub={isAdmin ? "As Admin, this change is applied immediately and recorded in the ledger and audit log."
        : "Your change is sent to the Admin and applied only after the Admin approves it."}
      footer={<><button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={submit.isPending || reason.trim().length < 3} onClick={send}>
          {isAdmin ? "Apply change" : "Send for approval"}</button></>}>
      <div className="flex flex-col gap-3">
        <Field label="Medicine">
          <select className="input" value={medicineId} onChange={(e) => setMedicineId(Number(e.target.value))}>
            {medicines.map((m) => <option key={m.id} value={m.id}>{m.name} (stock {m.stock}, rate {Number(m.rate) > 0 ? money(m.rate) : "not set"})</option>)}
          </select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Adjustment type">
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {(["add", "remove", "set_count", "set_rate"] as Kind[]).map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
            </select>
          </Field>
          {kind === "set_rate"
            ? <Field label="New selling rate (₹)"><input className="input" type="number" step="0.01" min="0.01" value={rate} onChange={(e) => setRate(e.target.value)} /></Field>
            : <Field label={kind === "set_count" ? "Counted quantity" : "Quantity"}><input className="input" type="number" min={kind === "set_count" ? 0 : 1} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></Field>}
        </div>
        <Field label="Reason / reference">
          <input className="input" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="Purchase invoice no., expiry, damage, count sheet…" />
        </Field>
      </div>
    </Modal>
  );
}

import type { Bill } from "../api/types";
import { money } from "./format";

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export function printReceipt(b: Bill, hospitalName: string): boolean {
  const w = window.open("", "_blank", "width=700,height=750");
  if (!w) return false;
  const when = new Date(b.created_at).toLocaleString("en-IN");
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(b.bill_no)}</title><style>
body{font:13px Arial,sans-serif;color:#222;padding:28px;max-width:650px;margin:auto}.c{text-align:center}.line{border-top:1px dashed #999;margin:15px 0}
table{width:100%;border-collapse:collapse}td,th{padding:8px 4px;border-bottom:1px solid #ddd;text-align:left}th:last-child,td:last-child{text-align:right}
.total{text-align:right;font-size:18px;font-weight:bold;margin-top:15px}.s{font-size:11px;color:#555}.rev{border:2px solid #a94f4b;color:#a94f4b;text-align:center;font-weight:bold;padding:6px;margin-bottom:10px}
</style></head><body>
${b.status === "reversed" ? `<div class="rev">REVERSED · ${esc(b.reversal_ref)} · ${esc(b.reversal_reason)}</div>` : ""}
<div class="c"><h2 style="margin-bottom:2px">${esc(hospitalName.toUpperCase())}</h2><div class="s">Dispensary billing receipt</div></div><div class="line"></div>
<div>Bill: <b>${esc(b.bill_no)}</b><span style="float:right">${esc(when)}</span></div>
<div style="margin-top:7px">Customer: ${esc(b.customer_name || "Walk-in customer")}${b.patient_ref ? " · ID: " + esc(b.patient_ref) : ""}</div><div class="line"></div>
<table><thead><tr><th>Medicine</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>
${b.items.map((i) => `<tr><td>${esc(i.medicine_name)}</td><td>${i.qty} ${esc(i.unit)}</td><td>${money(i.rate)}</td><td>${money(i.amount)}</td></tr>`).join("")}
</tbody></table><div class="total">Total: ${money(b.total)}</div><div class="s" style="text-align:right">Payment: ${esc(b.payment_mode)}</div>
<div class="line"></div><div class="s">Issued by: ${esc(b.operator_name)} · ${esc(b.terminal)}</div><p class="c s" style="margin-top:30px">Thank you.</p>
</body></html>`);
  w.document.close();
  w.focus();
  w.print(); // called from the opener: no inline script, compatible with a strict Content-Security-Policy
  return true;
}

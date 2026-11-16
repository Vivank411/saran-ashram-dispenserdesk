export const money = (v: string | number | null | undefined) =>
  "₹" + Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtDateTime = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s.length === 10 ? s + "T00:00:00" : s).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const fmtTime = (s: string) => new Date(s).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

export function ago(s: string | null | undefined): string {
  if (!s) return "never";
  const d = (Date.now() - new Date(s).getTime()) / 1000;
  if (d < 10) return "just now";
  if (d < 60) return `${Math.floor(d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
}

export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const KIND_LABELS: Record<string, string> = {
  add: "Add stock (receipt)", remove: "Remove stock (expiry/damage)", set_count: "Physical count correction", set_rate: "Change selling rate",
  bill_issue: "Bill issue", bill_reversal: "Bill reversal", receipt: "Stock receipt", write_off: "Write-off",
  count_correction: "Count correction", rate_change: "Rate change", opening: "Opening balance",
};

export function downloadCSV(rows: (string | number)[][], name: string) {
  const csv = rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

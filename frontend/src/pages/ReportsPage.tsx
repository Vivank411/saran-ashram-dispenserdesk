import { useState } from "react";
import type { Report } from "../api/types";
import { Icon } from "../components/Icon";
import { PageHeader, Panel, SourceBadge, Stat, Table, Tabs } from "../components/ui";
import { downloadCSV, fmtDate, money, todayISO } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";

type Period = "day" | "month" | "year";

export default function ReportsPage() {
  const { data: status } = useStatus();
  const [period, setPeriod] = useState<Period>("day");
  const [day, setDay] = useState(todayISO());
  const { data: r } = useGet<Report>(["report"], "/reports/dispensing", { period, day });
  const maxQty = Math.max(1, ...(r?.items ?? []).map((i) => i.qty));

  function onPick(v: string) {
    if (!v) return;
    setDay(period === "day" ? v : period === "month" ? `${v}-01` : `${v}-01-01`);
  }

  return (
    <>
      <PageHeader title="Dispensing reports" sub="Medicine-wise quantities and billing totals for any day, month or year."
        actions={<>
          <SourceBadge source={r?.source} lastSync={status?.last_sync} />
          <button className="btn" disabled={!r?.items.length} onClick={() => r && downloadCSV(
            [["Medicine", "Unit", "Quantity dispensed", "Current stock", "Billed value"], ...r.items.map((i) => [i.medicine_name, i.unit, i.qty, i.current_stock ?? "", i.amount])],
            `dispensing-${period}-${day}.csv`)}><Icon name="download" />Export CSV</button>
        </>} />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Tabs value={period} onChange={setPeriod} tabs={[["day", "Daily"], ["month", "Monthly"], ["year", "Yearly"]]} />
        <input className="input w-auto" aria-label="Report period" type={period === "day" ? "date" : period === "month" ? "month" : "number"}
          min={period === "year" ? 2000 : undefined} max={period === "year" ? 2100 : undefined}
          value={period === "day" ? day : period === "month" ? day.slice(0, 7) : day.slice(0, 4)} onChange={(e) => onPick(e.target.value)} />
        {r && <span className="text-[13px] text-muted">{fmtDate(r.start)}{r.start !== r.end && <> – {fmtDate(r.end)}</>}</span>}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Stat label="Total billed" value={money(r?.total)} icon="rupee" tone="accent" note="Net of reversed bills" />
        <Stat label="Bills" value={r?.bills ?? "—"} icon="bills" tone="info" note={`${r?.reversed_bills ?? 0} reversed, excluded`} />
        <Stat label="Units dispensed" value={r?.units ?? "—"} icon="pill" tone="slate" note="Sum of all quantities" />
        <Stat label="Medicines dispensed" value={r?.distinct_medicines ?? "—"} icon="layers" tone="good" note="Distinct medicine types" />
      </div>

      <Panel title="Medicine-wise dispensing" sub="Sorted by quantity issued" flush>
        <Table colSpan={5} empty="No dispensing in this period."
          head={<><th>Medicine</th><th>Unit</th><th className="w-[38%]">Quantity dispensed</th><th className="num">Current stock</th><th className="num">Billed value</th></>}>
          {r?.items.map((i) => (
            <tr key={i.medicine_id} title={`${i.medicine_name}: ${i.qty} ${i.unit} · ${money(i.amount)}`}>
              <td className="font-semibold text-ink">{i.medicine_name}</td>
              <td>{i.unit}</td>
              <td>
                <div className="flex items-center gap-3">
                  <span className="h-2 flex-1 rounded-full bg-slate-100"><span className="block h-2 rounded-full bg-accent" style={{ width: `${(i.qty / maxQty) * 100}%` }} /></span>
                  <span className="w-12 text-right font-semibold text-ink tnum">{i.qty}</span>
                </div>
              </td>
              <td className="num">{i.current_stock}</td>
              <td className="num font-semibold text-ink">{money(i.amount)}</td>
            </tr>
          ))}
        </Table>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">Totals come from confirmed bills only. Stock adjustments are tracked separately in the movement ledger.</p>
      </Panel>
    </>
  );
}

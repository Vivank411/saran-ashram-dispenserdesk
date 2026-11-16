import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Listing, Medicine, Movement } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import AdjustmentModal from "../components/AdjustmentModal";
import CsvStockModal from "../components/CsvStockModal";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Notice, PageHeader, Panel, SearchInput, SourceBadge, Stat, StockPill, Table, Tabs } from "../components/ui";
import { fmtDateTime, KIND_LABELS, money } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";

type Filter = "all" | "low" | "out";

export default function StockPage() {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: status } = useStatus();
  const [tab, setTab] = useState<"register" | "ledger">("register");
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [requestFor, setRequestFor] = useState<number | null | undefined>(undefined);
  const [showCsvModal, setShowCsvModal] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const meds = useGet<Listing<Medicine>>(["medicines"], "/medicines");
  const ledger = useGet<Listing<Movement>>(["movements"], "/movements", { q, limit: 300 }, { enabled: tab === "ledger" });
  const th = status?.low_stock_threshold ?? 50;
  const all = meds.data?.items ?? [];
  const rows = all.filter((m) => `${m.name} ${m.code} ${m.company}`.toLowerCase().includes(q.toLowerCase()))
    .filter((m) => filter === "all" || (filter === "low" ? m.stock > 0 && m.stock <= th : m.stock <= 0));
  const canChange = can("stock.request") && (status?.live_operations ?? true);
  const isAdmin = can("stock.approve");

  async function handleExportCsv() {
    setIsExporting(true);
    try {
      const res = await api.get("/medicines/export-csv", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `stock_register_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast("Stock register CSV downloaded");
    } catch {
      toast("Failed to export CSV", "error");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <>
      <PageHeader title="Stock & ledger"
        sub={isAdmin ? "Medicine register and full movement history. Your changes apply immediately and are recorded in the ledger."
          : "Medicine register and movement history. Stock changes you request are applied after Admin approval."}
        actions={
          <>
            <SourceBadge source={meds.data?.source} lastSync={status?.last_sync} />
            <button
              className="btn"
              onClick={handleExportCsv}
              disabled={isExporting}
              title="Download stock register as CSV"
            >
              <Icon name="download" className="h-4 w-4" />
              {isExporting ? "Exporting..." : "Export CSV"}
            </button>
            {canChange && (
              <>
                {isAdmin && (
                  <button
                    className="btn"
                    onClick={() => setShowCsvModal(true)}
                    title="Bulk update or upload stock from CSV spreadsheet"
                  >
                    <Icon name="upload" className="h-4 w-4" />
                    Upload CSV
                  </button>
                )}
                <button className="btn btn-primary" onClick={() => setRequestFor(null)}>
                  <Icon name="plus" />
                  {isAdmin ? "Adjust stock" : "Request change"}
                </button>
              </>
            )}
          </>
        } />
      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Stat label="Medicines" value={all.length} icon="pill" tone="accent" note="In the stock register" />
        <Stat label="Healthy stock" value={all.filter((m) => m.stock > th).length} icon="checkCircle" tone="good" note={`Above ${th} units`} />
        <Stat label="Low stock" value={all.filter((m) => m.stock > 0 && m.stock <= th).length} icon="alert" tone="warn" note={`1 – ${th} units`} />
        <Stat label="Out of stock" value={all.filter((m) => m.stock <= 0).length} icon="alertCircle" tone="danger" note="Zero or negative balance" />
      </div>
      <Panel flush toolbar={<>
        <Tabs value={tab} onChange={setTab} tabs={[["register", "Register"], ["ledger", "Movement ledger"]]} />
        <SearchInput value={q} onChange={setQ} placeholder={tab === "register" ? "Search medicine, code or company" : "Search medicine or reference"} className="max-w-xs" />
        {tab === "register" && (
          <select className="input w-auto" value={filter} onChange={(e) => setFilter(e.target.value as Filter)} aria-label="Filter by stock level">
            <option value="all">All stock levels</option><option value="low">Low stock only</option><option value="out">Out of stock only</option>
          </select>
        )}
        <span className="ml-auto text-[13px] text-muted tnum">{tab === "register" ? rows.length : ledger.data?.items.length ?? 0} results</span>
      </>}>
        {tab === "register" ? (
          <Table colSpan={10} empty="No medicines match your search." maxHeight="calc(100vh - 320px)"
            head={<><th>Code</th><th>Medicine</th><th>Unit</th><th className="num">In stock</th><th className="num">Selling rate</th>
              <th className="num">Cost</th><th className="num">MRP</th><th>Company</th><th>Status</th><th /></>}>
            {rows.map((m) => (
              <tr key={m.id}>
                <td className="text-muted tnum">{m.code}</td>
                <td className="font-semibold text-ink">{m.name}</td>
                <td>{m.unit}</td>
                <td className={`num font-semibold ${m.stock <= 0 ? "text-danger" : m.stock <= th ? "text-warn" : "text-ink"}`}>{m.stock}</td>
                <td className="num">{Number(m.rate) > 0 ? money(m.rate) : <span className="pill pill-warn">No rate</span>}</td>
                <td className="num text-muted">{Number(m.cost) > 0 ? money(m.cost) : "—"}</td>
                <td className="num text-muted">{Number(m.mrp) > 0 ? money(m.mrp) : "—"}</td>
                <td className="text-muted">{m.company || "—"}</td>
                <td><StockPill stock={m.stock} threshold={th} /></td>
                <td>{canChange && <button className="btn btn-sm" onClick={() => setRequestFor(m.id)}><Icon name="edit" className="h-3.5 w-3.5" />{isAdmin ? "Adjust" : "Request"}</button>}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <Table colSpan={8} empty="No stock movements yet." maxHeight="calc(100vh - 320px)"
            head={<><th>Time</th><th>Medicine</th><th>Movement</th><th className="num">Change</th><th className="num">Balance</th><th>Reference</th><th>By</th><th>Counter</th></>}>
            {ledger.data?.items.map((m) => (
              <tr key={m.id}>
                <td>{fmtDateTime(m.created_at)}</td>
                <td className="font-semibold text-ink">{m.medicine_name}</td>
                <td>{KIND_LABELS[m.kind] ?? m.kind}{m.note && <div className="text-xs text-muted">{m.note}</div>}</td>
                <td className={`num font-semibold ${m.qty_change < 0 ? "text-danger" : m.qty_change > 0 ? "text-good" : ""}`}>{m.qty_change > 0 ? "+" : ""}{m.qty_change}</td>
                <td className="num">{m.balance_after}</td>
                <td className="font-mono text-xs">{m.reference}</td>
                <td>{m.user_name}</td>
                <td>{m.terminal}</td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
      <Notice tone="warn">The imported register includes some zero and negative balances. They are kept exactly as supplied — correct them with a physical count adjustment before going live.</Notice>
      {requestFor !== undefined && <AdjustmentModal medicines={all} initialId={requestFor} onClose={() => setRequestFor(undefined)} />}
      {showCsvModal && (
        <CsvStockModal
          onClose={() => setShowCsvModal(false)}
          onSuccess={() => qc.invalidateQueries()}
        />
      )}
    </>
  );
}

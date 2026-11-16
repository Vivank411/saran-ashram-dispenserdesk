import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, newRequestId, toApiError } from "../api/client";
import type { Bill, Listing, Medicine } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Field, Notice, PageHeader, Panel, SourceBadge } from "../components/ui";
import { fmtDateTime, fmtTime, money } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";
import { printReceipt } from "../lib/receipt";

/**
 * Multi-bill counter. Each open bill (draft) stores only medicine ids + quantities; names, rates and stock are always
 * read from the live inventory, so a draft never bills at an outdated price. Quantities in other open bills are
 * shown as reserved so the biller does not promise the same units twice. The server re-checks stock on confirm.
 */
interface DraftLine { medicineId: number; qty: number }
interface Draft { id: string; no: number; customer: string; patientRef: string; payment: string; requestId: string; lines: DraftLine[] }

const PAYMENTS = ["Cash", "UPI", "Card", "Other"] as const;
const MAX_OPEN = 8;

const newDraft = (no: number): Draft => ({ id: newRequestId(), no, customer: "", patientRef: "", payment: "Cash", requestId: newRequestId(), lines: [] });

function load<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
}

export default function NewBillPage() {
  const { session, user } = useAuth();
  const { data: status } = useStatus();
  const toast = useToast();
  const qc = useQueryClient();
  const isCloud = status?.role === "cloud";
  const live = status?.live_operations ?? true;
  const meds = useGet<Listing<Medicine>>(["medicines", "live"], "/medicines", isCloud ? { live: true } : undefined,
    { enabled: !!status && live, refetchInterval: 15_000 });

  const draftsKey = `dd_open_bills_${user?.id}`;
  const recentKey = `dd_recent_bills_${user?.id}`;
  const [drafts, setDrafts] = useState<Draft[]>(() => {
    const saved = load<Draft[]>(draftsKey, []);
    return saved.length ? saved : [newDraft(1)];
  });
  const [activeId, setActiveId] = useState<string>(() => drafts[0].id);
  const [recent, setRecent] = useState<Bill[]>(() => load<Bill[]>(recentKey, []));
  const [query, setQuery] = useState("");
  const [hi, setHi] = useState(0);
  const [saving, setSaving] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => { try { localStorage.setItem(draftsKey, JSON.stringify(drafts)); } catch { /* storage unavailable */ } }, [drafts, draftsKey]);
  useEffect(() => { try { localStorage.setItem(recentKey, JSON.stringify(recent)); } catch { /* storage unavailable */ } }, [recent, recentKey]);
  useEffect(() => { if (!drafts.some((d) => d.id === activeId)) setActiveId(drafts[0].id); }, [drafts, activeId]);

  const draft = drafts.find((d) => d.id === activeId) ?? drafts[0];
  const byId = useMemo(() => new Map((meds.data?.items ?? []).map((m) => [m.id, m])), [meds.data]);
  const reservedElsewhere = (medId: number, draftId: string) =>
    drafts.filter((d) => d.id !== draftId).reduce((a, d) => a + (d.lines.find((l) => l.medicineId === medId)?.qty ?? 0), 0);
  const available = (m: Medicine, draftId = draft.id) => m.stock - reservedElsewhere(m.id, draftId);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const billable = (m: Medicine) => m.stock > 0 && Number(m.rate) > 0;
    return (meds.data?.items ?? [])
      .filter((m) => m.name.toLowerCase().includes(q) || String(m.code) === q)
      .sort((a, b) => Number(billable(b)) - Number(billable(a))
        || Number(b.name.toLowerCase().startsWith(q)) - Number(a.name.toLowerCase().startsWith(q))
        || a.name.localeCompare(b.name))
      .slice(0, 10);
  }, [query, meds.data]);
  useEffect(() => setHi(0), [query]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") { e.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (status && !live) {
    return (
      <>
        <PageHeader title="New bill" sub="Create a separate transaction for each customer." />
        <Panel>
          <div className="mx-auto max-w-md py-8 text-center">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-danger-soft text-danger"><Icon name="cloudOff" className="h-6 w-6" /></span>
            <h2 className="mt-4 text-lg font-semibold text-ink">Live billing is temporarily unavailable</h2>
            <p className="mt-2 text-muted">Bills can only be confirmed against live stock on the hospital server, so stock is never deducted from out-of-date figures.
              Open bills are kept and can be confirmed when the connection returns.</p>
            <p className="mt-2 text-xs text-muted">Last synchronized {fmtDateTime(status.last_sync)}</p>
            <Link className="btn mt-5" to="/reports">View last synchronized reports</Link>
          </div>
        </Panel>
      </>
    );
  }

  // ---------- draft helpers ----------
  const patch = (id: string, change: Partial<Draft> | ((d: Draft) => Partial<Draft>)) =>
    setDrafts((ds) => ds.map((d) => (d.id === id ? { ...d, ...(typeof change === "function" ? change(d) : change) } : d)));

  function openNew() {
    if (drafts.length >= MAX_OPEN) return toast(`You can keep up to ${MAX_OPEN} bills open at once.`, "error");
    const d = newDraft(Math.max(0, ...drafts.map((x) => x.no)) + 1);
    setDrafts([...drafts, d]);
    setActiveId(d.id);
    setQuery("");
    setTimeout(() => searchRef.current?.focus(), 0);
  }

  function closeDraft(id: string) {
    const d = drafts.find((x) => x.id === id)!;
    if (d.lines.length && !confirm(`Discard Bill ${d.no}? Its ${d.lines.length} item(s) will be removed.`)) return;
    const rest = drafts.filter((x) => x.id !== id);
    setDrafts(rest.length ? rest : [newDraft(d.no + 1)]);
  }

  function add(m: Medicine) {
    if (Number(m.rate) <= 0) return toast(`No selling rate is set for ${m.name}. Request a rate change first.`, "error");
    const free = available(m) - (draft.lines.find((l) => l.medicineId === m.id)?.qty ?? 0);
    if (free <= 0) return toast(m.stock <= 0 ? `${m.name} is out of stock.` : `All ${m.stock} units of ${m.name} are already in other open bills.`, "error");
    patch(draft.id, (d) => {
      const i = d.lines.findIndex((l) => l.medicineId === m.id);
      return { lines: i >= 0 ? d.lines.map((l, j) => (j === i ? { ...l, qty: l.qty + 1 } : l)) : [...d.lines, { medicineId: m.id, qty: 1 }] };
    });
    setQuery("");
    searchRef.current?.focus();
  }

  function setQty(medId: number, value: number) {
    const m = byId.get(medId);
    let qty = Number.isFinite(value) && value >= 1 ? Math.floor(value) : 1;
    if (m) {
      const max = Math.max(1, available(m));
      if (qty > max) { toast(`Only ${Math.max(0, available(m))} ${m.unit} of ${m.name} available for this bill.`, "error"); qty = max; }
    }
    patch(draft.id, (d) => ({ lines: d.lines.map((l) => (l.medicineId === medId ? { ...l, qty } : l)) }));
  }

  // Live check of every line against current inventory.
  const lineIssue = (l: DraftLine, d: Draft): string | null => {
    const m = byId.get(l.medicineId);
    if (!meds.data) return null;
    if (!m) return "No longer in the stock register";
    if (Number(m.rate) <= 0) return "No selling rate set";
    if (l.qty > m.stock) return `Only ${m.stock} left in stock`;
    if (l.qty > available(m, d.id)) return `${reservedElsewhere(m.id, d.id)} also held in other open bills`;
    return null;
  };
  const blocking = (l: DraftLine, _d?: Draft) => {
    const m = byId.get(l.medicineId);
    return !!meds.data && (!m || Number(m.rate) <= 0 || l.qty > m.stock);
  };
  const totals = (d: Draft) => d.lines.reduce((a, l) => {
    const m = byId.get(l.medicineId);
    return { units: a.units + l.qty, amount: a.amount + (m ? l.qty * Number(m.rate) : 0) };
  }, { units: 0, amount: 0 });

  async function confirmBill(d: Draft) {
    if (!d.lines.length) return toast("Add at least one medicine.", "error");
    if (d.lines.some((l) => blocking(l, d))) return toast("Fix the highlighted lines before confirming.", "error");
    setSaving(d.id);
    try {
      const { data } = await api.post<{ bill: Bill; alerts: string[]; duplicate: boolean }>("/bills", {
        request_id: d.requestId, customer_name: d.customer, patient_ref: d.patientRef, payment_mode: d.payment,
        items: d.lines.map((l) => ({ medicine_id: l.medicineId, qty: l.qty })),
      });
      toast(data.duplicate ? `${data.bill.bill_no} was already saved.` : `${data.bill.bill_no} confirmed · ${money(data.bill.total)}`);
      data.alerts.forEach((a) => toast(a, "warn"));
      setRecent((r) => [data.bill, ...r.filter((b) => b.id !== data.bill.id)].slice(0, 8));
      setDrafts((ds) => { const rest = ds.filter((x) => x.id !== d.id); return rest.length ? rest : [newDraft(d.no + 1)]; });
      await meds.refetch(); // other open bills immediately see the reduced stock
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "medicines" });
    } catch (e) {
      const err = toApiError(e);
      toast(err.message, "error");
      if (err.code === "INSUFFICIENT_STOCK" || err.code === "NO_RATE") meds.refetch();
    } finally {
      setSaving(null);
    }
  }

  const t = totals(draft);
  const hasBlocking = draft.lines.some((l) => blocking(l, draft));
  const hospital = status?.hospital_name ?? "Hospital Dispensary";

  return (
    <>
      <PageHeader title="New bill"
        sub={isCloud ? "Remote billing — each bill is confirmed directly on the hospital server." : `Counter ${session?.terminal} · keep several bills open and confirm each when ready.`}
        actions={<SourceBadge source={meds.data?.source} />} />

      {/* open bills */}
      <div className="mb-5 flex items-center gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Open bills">
        {drafts.map((d) => {
          const dt = totals(d);
          const sel = d.id === draft.id;
          const warn = d.lines.some((l) => blocking(l, d));
          return (
            <div key={d.id} role="tab" aria-selected={sel} tabIndex={0} onClick={() => setActiveId(d.id)} onKeyDown={(e) => e.key === "Enter" && setActiveId(d.id)}
              className={`group flex shrink-0 cursor-pointer items-center gap-3 rounded-xl border py-2 pl-3.5 pr-2 transition ${sel ? "border-accent bg-white shadow-card ring-2 ring-accent/15" : "border-line bg-white/60 hover:bg-white"}`}>
              <span className={`grid h-7 w-7 place-items-center rounded-lg text-[12px] font-bold ${sel ? "bg-accent text-white" : "bg-slate-100 text-slate-600"}`}>{d.no}</span>
              <span className="leading-tight">
                <span className="block max-w-[140px] truncate text-[13px] font-semibold text-ink">{d.customer || `Bill ${d.no}`}</span>
                <span className="block text-[11.5px] text-muted tnum">{d.lines.length ? `${d.lines.length} item${d.lines.length > 1 ? "s" : ""} · ${money(dt.amount)}` : "Empty"}</span>
              </span>
              {warn && <Icon name="alert" className="h-4 w-4 text-warn" />}
              <button className="grid h-6 w-6 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label={`Close Bill ${d.no}`}
                onClick={(e) => { e.stopPropagation(); closeDraft(d.id); }}><Icon name="x" className="h-3.5 w-3.5" /></button>
            </div>
          );
        })}
        <button className="btn shrink-0 border-dashed" onClick={openNew} disabled={drafts.length >= MAX_OPEN}><Icon name="plus" />Open another bill</button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0">
          <Panel title={`Bill ${draft.no} · Patient`} sub="Optional — printed on the receipt">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Customer / patient name"><input className="input" value={draft.customer} maxLength={80} placeholder="Walk-in customer"
                onChange={(e) => patch(draft.id, { customer: e.target.value })} /></Field>
              <Field label="Patient / OPD ID"><input className="input" value={draft.patientRef} maxLength={40} placeholder="e.g. OPD-2026-0142"
                onChange={(e) => patch(draft.id, { patientRef: e.target.value })} /></Field>
            </div>
          </Panel>

          <Panel title="Medicines" sub={`${draft.lines.length} item${draft.lines.length === 1 ? "" : "s"} in Bill ${draft.no} · prices and stock are live from inventory`} flush clip={false}
            toolbar={
              <div className="relative w-full">
                <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400" />
                <input ref={searchRef} className="input h-11 pl-11 pr-24 text-[14px]" autoComplete="off" autoFocus
                  placeholder={meds.isLoading ? "Loading stock…" : "Search medicine by name or code"} value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") { e.preventDefault(); setHi((a) => Math.min(a + 1, matches.length - 1)); }
                    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((a) => Math.max(a - 1, 0)); }
                    else if (e.key === "Enter" && matches[hi]) { e.preventDefault(); add(matches[hi]); }
                    else if (e.key === "Escape") setQuery("");
                  }}
                  aria-label="Search medicine" aria-expanded={!!query} />
                <span className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-1 text-[11px] text-muted sm:flex">
                  <span className="kbd">/</span> to search</span>
                {query && (
                  <div className="absolute left-0 right-0 top-full z-10 mt-1.5 max-h-80 overflow-auto rounded-xl border border-line bg-white p-1 shadow-pop" role="listbox">
                    {matches.length ? matches.map((m, i) => {
                      const free = available(m);
                      const bad = free <= 0 || Number(m.rate) <= 0;
                      return (
                        <button key={m.id} role="option" aria-selected={i === hi} onMouseEnter={() => setHi(i)} onClick={() => add(m)}
                          className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left ${i === hi ? "bg-accent-soft" : ""} ${bad ? "opacity-55" : ""}`}>
                          <span className="flex min-w-0 items-center gap-3">
                            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500"><Icon name="pill" /></span>
                            <span className="min-w-0"><b className="block truncate text-[13.5px] text-ink">{m.name}</b>
                              <span className="text-xs text-muted">{m.unit} · Code {m.code}</span></span>
                          </span>
                          <span className="text-right">
                            <b className="block text-[13.5px] text-ink tnum">{Number(m.rate) > 0 ? money(m.rate) : "No rate"}</b>
                            <span className={`text-xs tnum ${free <= 0 ? "text-danger" : "text-muted"}`}>
                              {m.stock <= 0 ? "Unavailable" : free < m.stock ? `${Math.max(0, free)} free · ${m.stock - free} in open bills` : `${m.stock} in stock`}
                            </span>
                          </span>
                        </button>
                      );
                    }) : <div className="px-3 py-3 text-[13px] text-muted">No matching medicine in the stock register.</div>}
                  </div>
                )}
              </div>
            }>
            {draft.lines.length ? (
              <div className="overflow-x-auto">
                <table className="tbl">
                  <thead><tr><th>Medicine</th><th className="num">Rate</th><th className="text-center">Quantity</th><th className="num">Amount</th><th /></tr></thead>
                  <tbody>
                    {draft.lines.map((l) => {
                      const m = byId.get(l.medicineId);
                      const issue = lineIssue(l, draft);
                      const block = blocking(l, draft);
                      return (
                        <tr key={l.medicineId} className={block ? "bg-danger-soft/50" : ""}>
                          <td>
                            <div className="font-semibold text-ink">{m?.name ?? `Medicine #${l.medicineId}`}</div>
                            <div className="text-xs text-muted">{m ? `${m.unit} · ${Math.max(0, available(m))} available` : "—"}</div>
                            {issue && <div className={`mt-1 flex items-center gap-1 text-xs font-medium ${block ? "text-danger" : "text-warn"}`}>
                              <Icon name="alert" className="h-3.5 w-3.5" />{issue}</div>}
                          </td>
                          <td className="num">{m ? money(m.rate) : "—"}</td>
                          <td>
                            <div className="mx-auto flex w-[128px] items-center rounded-lg border border-line-strong bg-white">
                              <button className="grid h-8 w-8 place-items-center text-muted hover:text-ink disabled:opacity-40" disabled={l.qty <= 1}
                                onClick={() => setQty(l.medicineId, l.qty - 1)} aria-label="Decrease"><Icon name="minus" /></button>
                              <input className="h-8 w-full min-w-0 border-x border-line bg-transparent text-center text-[13.5px] font-semibold outline-none tnum"
                                type="number" min={1} value={l.qty} onChange={(e) => setQty(l.medicineId, Number(e.target.value))}
                                aria-label={`Quantity of ${m?.name ?? l.medicineId}`} />
                              <button className="grid h-8 w-8 place-items-center text-muted hover:text-ink disabled:opacity-40" disabled={!m || l.qty >= available(m)}
                                onClick={() => setQty(l.medicineId, l.qty + 1)} aria-label="Increase"><Icon name="plus" /></button>
                            </div>
                          </td>
                          <td className="num font-semibold text-ink">{m ? money(l.qty * Number(m.rate)) : "—"}</td>
                          <td className="w-10"><button className="btn btn-ghost btn-sm px-1.5 text-muted hover:text-danger"
                            onClick={() => patch(draft.id, (d) => ({ lines: d.lines.filter((x) => x.medicineId !== l.medicineId) }))}
                            aria-label={`Remove ${m?.name ?? "item"}`}><Icon name="trash" /></button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
                <span className="grid h-12 w-12 place-items-center rounded-full bg-accent-soft text-accent"><Icon name="search" className="h-5 w-5" /></span>
                <div className="font-semibold text-ink">Search for a medicine to add it to Bill {draft.no}</div>
                <div className="text-[13px] text-muted">Use ↑ ↓ and Enter. Adding the same medicine again increases its quantity.</div>
              </div>
            )}
          </Panel>
        </div>

        <div className="xl:sticky xl:top-24 xl:self-start">
          <section className="panel">
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h2 className="text-[15px] font-semibold text-ink">Bill {draft.no} summary</h2>
              {drafts.length > 1 && <span className="pill pill-grey">{drafts.length} open bills</span>}
            </div>
            <div className="space-y-2.5 px-5 py-4 text-[13.5px]">
              <div className="flex justify-between"><span className="text-muted">Medicines</span><span className="font-medium tnum">{draft.lines.length}</span></div>
              <div className="flex justify-between"><span className="text-muted">Total units</span><span className="font-medium tnum">{t.units}</span></div>
            </div>
            <div className="mx-5 flex items-end justify-between rounded-xl bg-accent-soft px-4 py-4">
              <span className="text-[13px] font-medium text-accent-dark">Total payable</span>
              <span className="text-[28px] font-semibold leading-none tracking-tight text-ink tnum">{money(t.amount)}</span>
            </div>
            <div className="px-5 pt-5">
              <div className="label mb-2">Payment mode</div>
              <div className="grid grid-cols-4 gap-1.5" role="radiogroup" aria-label="Payment mode">
                {PAYMENTS.map((p) => (
                  <button key={p} role="radio" aria-checked={draft.payment === p} onClick={() => patch(draft.id, { payment: p })}
                    className={`h-9 rounded-lg border text-[13px] font-semibold transition ${draft.payment === p ? "border-accent bg-accent text-white" : "border-line-strong bg-white text-ink-soft hover:bg-slate-50"}`}>{p}</button>
                ))}
              </div>
            </div>
            <div className="px-5 pb-5 pt-5">
              <button className="btn btn-primary btn-lg w-full" disabled={!!saving || !draft.lines.length || hasBlocking} onClick={() => confirmBill(draft)}>
                <Icon name="check" />{saving === draft.id ? "Confirming…" : `Confirm Bill ${draft.no}`}
              </button>
              {hasBlocking && <p className="mt-2 text-xs font-medium text-danger">Some items no longer match current stock — adjust them to continue.</p>}
              <p className="mt-3 flex gap-2 text-[11.5px] leading-relaxed text-muted"><Icon name="shield" className="mt-0.5 h-3.5 w-3.5" />
                Stock is re-checked and deducted in one secure transaction. Pressing twice never creates a duplicate bill.</p>
            </div>
          </section>

          <Panel title="Confirmed recently" sub="Print a receipt whenever the customer needs one" flush>
            {recent.length ? (
              <ul className="divide-y divide-line">
                {recent.map((b) => (
                  <li key={b.id} className="flex items-center gap-3 px-5 py-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-good-soft text-good"><Icon name="check" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-semibold text-ink">{b.bill_no}</div>
                      <div className="truncate text-xs text-muted">{b.customer_name || "Walk-in"} · {fmtTime(b.created_at)} · <span className="tnum">{money(b.total)}</span></div>
                    </div>
                    <button className="btn btn-sm" onClick={() => printReceipt(b, hospital) || toast("Allow pop-ups to print the receipt.", "error")}>
                      <Icon name="printer" className="h-3.5 w-3.5" />Print</button>
                  </li>
                ))}
              </ul>
            ) : <p className="px-5 py-5 text-[13px] text-muted">Bills you confirm appear here, ready to print.</p>}
            {recent.length > 0 && <div className="border-t border-line px-5 py-2.5 text-right"><Link className="text-[12.5px] font-semibold text-accent hover:underline" to="/bills">All bills →</Link></div>}
          </Panel>
          {!isCloud && status && !status.cloud_reachable && <Notice tone="warn">Offline: bills are fully valid and will sync to the cloud automatically later.</Notice>}
        </div>
      </div>
    </>
  );
}

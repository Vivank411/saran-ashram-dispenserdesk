import { useState } from "react";
import type { SyncDetail } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Dot, Notice, PageHeader, Panel, Stat, Table } from "../components/ui";
import { ago, fmtDateTime } from "../lib/format";
import { useAction, useGet } from "../lib/hooks";

const STATUS: Record<string, [string, "good" | "warn" | "bad" | "slate", string]> = {
  pending: ["pill-warn", "warn", "Pending"], failed: ["pill-bad", "bad", "Failed"], conflict: ["pill-bad", "bad", "Conflict"],
  synced: ["", "good", "Delivered"], resolved: ["pill-blue", "slate", "Resolved"],
};

export default function SyncPage() {
  const { can } = useAuth();
  const toast = useToast();
  const { data: s } = useGet<SyncDetail>(["sync"], "/sync/status", undefined, { refetchInterval: 5_000 });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const run = useAction<object, { status: string; applied?: number; duplicates?: number }>("post", "/sync/run", (r) =>
    toast(r.status === "ok" ? `Sync complete · ${r.applied ?? 0} change(s) delivered` : r.status === "offline" ? "Cloud unreachable — changes stay queued." : `Sync result: ${r.status}`,
      r.status === "ok" ? "ok" : "error"));
  const resolve = useAction<{ event_id: string; note: string }>("post", (b) => `/sync/conflicts/${b.event_id}/resolve`,
    () => toast("Conflict resolved — the cloud copy now matches the hospital."));
  const manage = can("sync.manage");
  const isCloud = s?.role === "cloud";
  const connected = isCloud ? s?.hospital_reachable : s?.cloud_reachable;
  const open = (s?.conflict_list ?? []).filter((c) => !c.resolved_at);

  return (
    <>
      <PageHeader title="Synchronization"
        sub={isCloud ? "Changes received from the hospital server — each applied exactly once, in order."
          : "Every confirmed change is queued with the transaction itself and delivered to the cloud in order. Nothing is lost while offline."}
        actions={manage && <button className="btn btn-primary" disabled={run.isPending || (isCloud && !connected)} onClick={() => run.mutate({})}>
          <Icon name="sync" className={`h-4 w-4 ${run.isPending ? "animate-spin" : ""}`} />Sync now</button>} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-5">
        <Stat label="Connection" value={<span className={connected ? "text-good" : "text-danger"}>{connected ? "Connected" : "Offline"}</span>}
          icon={connected ? "cloud" : "cloudOff"} tone={connected ? "good" : "danger"} note={isCloud ? "To hospital server" : "To cloud server"} />
        <Stat label="Last successful sync" value={ago(s?.last_sync)} icon="clock" tone="accent" note={fmtDateTime(s?.last_sync)} />
        <Stat label="Pending" value={s?.pending ?? "—"} icon="layers" tone="slate" note={isCloud ? "As reported by hospital" : "Waiting to be sent"} />
        <Stat label="Failed" value={s?.failed ?? "—"} icon="alert" tone="warn" note="Retried automatically" />
        <Stat label="Conflicts" value={s?.conflicts ?? 0} icon="alertCircle" tone={s?.conflicts ? "danger" : "good"} note={s?.conflicts ? "Paused — review below" : "None"} />
      </div>
      {s?.last_error && <Notice tone="warn">{s.last_error}</Notice>}

      {open.length > 0 && (
        <Panel title="Conflicts awaiting review" className="border-danger-line"
          sub="The cloud copy differs from what the hospital expected. Nothing was overwritten — the hospital is the source of truth for stock.">
          <div className="space-y-4">
            {open.map((c) => (
              <div key={c.event_id} className="rounded-xl border border-danger-line bg-danger-soft/40 p-4">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="pill pill-bad"><Dot tone="bad" />Conflict</span>
                  <b className="text-ink">{c.detail?.medicine_name ?? c.detail?.reason}</b>
                  <span className="text-muted">· change #{c.seq} ({c.event_type})</span>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-line bg-white px-3 py-2"><div className="text-xs text-muted">Cloud copy shows</div>
                    <div className="text-lg font-semibold text-ink tnum">{c.detail?.cloud_stock ?? "—"}</div></div>
                  <div className="rounded-lg border border-line bg-white px-3 py-2"><div className="text-xs text-muted">Hospital (correct) value</div>
                    <div className="text-lg font-semibold text-good tnum">{c.detail?.authoritative_stock ?? "—"}</div></div>
                </div>
                {manage ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <input className="input max-w-md flex-1" placeholder="Review note (required)" value={notes[c.event_id] ?? ""}
                      onChange={(e) => setNotes({ ...notes, [c.event_id]: e.target.value })} />
                    <button className="btn btn-primary" disabled={(notes[c.event_id] ?? "").trim().length < 3 || resolve.isPending}
                      onClick={() => resolve.mutate({ event_id: c.event_id, note: notes[c.event_id].trim() })}><Icon name="check" />Use hospital value & resume</button>
                  </div>
                ) : <p className="mt-3 text-xs text-muted">An Admin must review this conflict.</p>}
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title={isCloud ? "Received changes" : "Outgoing changes"} sub={`Latest 100 · ${s?.synced_total ?? 0} delivered in total`} flush>
        <Table colSpan={6} empty="No changes yet." maxHeight="560px"
          head={<><th>#</th><th>Change</th><th>Created</th><th>Status</th><th className="num">Attempts</th><th>Detail</th></>}>
          {s?.events.map((e) => {
            const [cls, dot, label] = STATUS[e.status] ?? ["pill-grey", "slate", e.status];
            return (
              <tr key={e.event_id}>
                <td className="text-muted tnum">{e.seq}</td>
                <td><div className="font-medium text-ink">{e.event_type}</div><div className="font-mono text-[11px] text-muted">{e.event_id.slice(0, 8)}</div></td>
                <td>{fmtDateTime(e.created_at)}</td>
                <td><span className={`pill ${cls}`}><Dot tone={dot} />{label}</span></td>
                <td className="num">{e.attempts ?? "—"}</td>
                <td className="max-w-md whitespace-normal text-xs">{e.status === "synced" ? `Delivered ${fmtDateTime(e.synced_at)}`
                  : e.status === "resolved" ? `Resolved${e.resolution ? ` by ${e.resolution.by} · ${e.resolution.note}` : ""}`
                  : `${e.last_error ?? "Waiting for connection"}${e.next_attempt_at ? ` · next try ${fmtDateTime(e.next_attempt_at)}` : ""}`}</td>
              </tr>
            );
          })}
        </Table>
      </Panel>
    </>
  );
}

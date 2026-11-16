import { useState } from "react";
import type { AuditEntry, Listing } from "../api/types";
import { PageHeader, Panel, SearchInput, Table } from "../components/ui";
import { fmtDateTime } from "../lib/format";
import { useGet, useStatus } from "../lib/hooks";

export default function AuditPage() {
  const { data: status } = useStatus();
  const [q, setQ] = useState("");
  const { data } = useGet<Listing<AuditEntry>>(["audit"], "/audit", { q, limit: 400 });
  const items = data?.items ?? [];
  return (
    <>
      <PageHeader title="Audit log" sub={status?.role === "cloud"
        ? "Remote sign-ins and account changes, plus every hospital event received through synchronization."
        : "Every sign-in (including offline), bill, reversal, stock change and administrative action on the hospital server."} />
      <Panel flush toolbar={<>
        <SearchInput value={q} onChange={setQ} placeholder="Search action, user or detail" className="max-w-md" />
        <span className="ml-auto text-[13px] text-muted tnum">{items.length} events</span>
      </>}>
        <Table colSpan={5} empty="No events match your search." maxHeight="calc(100vh - 260px)"
          head={<><th>Time</th><th>User</th><th>Action</th><th>Detail</th><th>Source</th></>}>
          {items.map((l) => (
            <tr key={l.id}>
              <td className="text-muted">{fmtDateTime(l.at)}</td>
              <td className="font-medium text-ink">{l.user_name}</td>
              <td className="font-semibold text-ink">{l.action}</td>
              <td className="min-w-[280px] max-w-[520px] whitespace-normal">{l.detail}</td>
              <td>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted">{l.channel === "remote" ? "Remote" : l.terminal}</span>
                  {l.offline && <span className="pill pill-grey">Offline</span>}
                  {l.origin === "cloud" ? <span className="pill pill-blue">Cloud</span> : !l.synced && <span className="pill pill-warn">Not synced</span>}
                </div>
              </td>
            </tr>
          ))}
        </Table>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">Audit entries are append-only: the application never edits or deletes them.</p>
      </Panel>
    </>
  );
}

import { useEffect, useState } from "react";
import { useToast } from "../components/Toasts";
import { Field, PageHeader, Panel } from "../components/ui";
import { useAction, useGet } from "../lib/hooks";

interface SettingsView {
  low_stock_threshold: number; session_hours: number; timezone: string; lockout_minutes: number;
  login_max_failures: number; otp_ttl_seconds: number; hospital_name: string;
}

export default function SettingsPage() {
  const toast = useToast();
  const { data } = useGet<SettingsView>(["settings"], "/settings");
  const [threshold, setThreshold] = useState("50");
  const [name, setName] = useState("");
  useEffect(() => {
    if (data) { setThreshold(String(data.low_stock_threshold)); setName(data.hospital_name); }
  }, [data]);
  const save = useAction<{ low_stock_threshold: number; hospital_name: string }>("put", "/settings", () => toast("Settings saved"));
  return (
    <>
      <PageHeader title="Settings" sub="Dispensary configuration (Admin)." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Dispensary" sub="Stored on the hospital server and synchronized to the cloud.">
          <div className="flex flex-col gap-3">
            <Field label="Hospital / dispensary name (shown on screens and receipts)">
              <input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Low-stock alert threshold (units)">
              <input className="input max-w-xs" type="number" min={0} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </Field>
          </div>
          <button className="btn btn-primary mt-4" disabled={save.isPending || name.trim().length < 2}
            onClick={() => save.mutate({ low_stock_threshold: Number(threshold), hospital_name: name.trim() })}>Save</button>
          <p className="mt-3 text-[11px] text-muted">A new threshold applies from the next transaction.</p>
        </Panel>
        <Panel title="Security policy" sub="Configured through environment variables on each server.">
          {data && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
              <dt className="text-muted">Session duration</dt><dd className="font-semibold">{data.session_hours} hours</dd>
              <dt className="text-muted">Account lockout</dt><dd className="font-semibold">{data.login_max_failures} failures → {data.lockout_minutes} min</dd>
              <dt className="text-muted">OTP validity</dt><dd className="font-semibold">{Math.round(data.otp_ttl_seconds / 60)} minutes</dd>
              <dt className="text-muted">Time zone</dt><dd className="font-semibold">{data.timezone}</dd>
            </dl>
          )}
        </Panel>
      </div>
    </>
  );
}

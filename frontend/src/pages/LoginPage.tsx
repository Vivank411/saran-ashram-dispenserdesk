import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, toApiError } from "../api/client";
import type { OtpRequired } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import entrance from "../assets/hospital-entrance.png";
import { Icon } from "../components/Icon";
import { Field, Notice } from "../components/ui";
import { ago } from "../lib/format";
import { useStatus } from "../lib/hooks";

type Mode = "loading" | "signup" | "signin";

export default function LoginPage() {
  const { login, verifyOtp, resendOtp, message } = useAuth();
  const { data: status } = useStatus();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("loading");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState<OtpRequired | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(message);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isCloud = status?.role === "cloud";
  const offline = status && !isCloud && !status.cloud_reachable;

  useEffect(() => {
    api.get<{ needs_setup: boolean }>("/auth/setup")
      .then(({ data }) => setMode(data.needs_setup ? "signup" : "signin"))
      .catch(() => setMode("signin"));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await login(username, password);
      if (result.status === "otp_required") setOtp(result);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await verifyOtp(otp!.challenge_id, code);
    } catch (err) {
      const apiErr = toApiError(err);
      setError(apiErr.message);
      if (apiErr.code === "OTP_STATE") setOtp(null);
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    try {
      setOtp(await resendOtp(otp!.challenge_id));
      setError(null);
    } catch (err) {
      setError(toApiError(err).message);
    }
  }

  function onSignedUp(newUsername: string) {
    setUsername(newUsername);
    setPassword("");
    setError(null);
    setInfo("Setup complete. Your Admin account is ready — sign in below.");
    setMode("signin");
    qc.invalidateQueries({ queryKey: ["status"] });
  }

  const hospitalName = status?.hospital_name ?? "Hospital Dispensary";
  return (
    <div className="min-h-screen bg-white lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(440px,1fr)]">
      {/* Hospital photo panel (desktop) */}
      <aside className="relative hidden overflow-hidden lg:block">
        <img src={entrance} alt={`${hospitalName} entrance`} className="absolute inset-0 h-full w-full scale-105 object-cover object-[center_45%]" />
        <div className="absolute inset-0 bg-gradient-to-t from-navy via-navy/60 to-navy/10" />
        <div className="absolute inset-0 bg-gradient-to-r from-navy/40 to-transparent" />
        <div className="relative flex h-full flex-col justify-between p-10 xl:p-14">
          <div className="flex items-center gap-3 text-white">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 ring-1 ring-white/25 backdrop-blur">
              <Icon name="pill" className="h-5 w-5" strokeWidth={2} />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">Dispensary Desk</span>
          </div>
          <div className="max-w-xl text-white">
            <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-teal-200">Hospital dispensary</p>
            <h2 className="text-[34px] font-semibold leading-tight tracking-tight xl:text-[40px]">{hospitalName}</h2>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-slate-200">
              Billing, medicine stock and dispensing records for the hospital — available at every counter, even without internet.
            </p>
            <ul className="mt-8 flex flex-wrap gap-2.5 text-[12.5px] font-medium">
              {([["shield", "Secure staff sign-in"], ["cloudOff", "Works offline"], ["sync", "Backed up to the cloud"]] as const).map(([icon, text]) => (
                <li key={text} className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 ring-1 ring-white/20 backdrop-blur">
                  <Icon name={icon} className="h-4 w-4 text-teal-200" />{text}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </aside>

      <main className="flex min-h-screen flex-col">
        {/* Hospital photo banner (mobile / tablet) */}
        <div className="relative h-48 overflow-hidden sm:h-56 lg:hidden">
          <img src={entrance} alt={`${hospitalName} entrance`} className="absolute inset-0 h-full w-full object-cover object-[center_45%]" />
          <div className="absolute inset-0 bg-gradient-to-t from-navy/90 via-navy/40 to-transparent" />
          <div className="absolute bottom-4 left-5 right-5 text-white">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-teal-200">Dispensary Desk</div>
            <div className="text-xl font-semibold leading-snug">{hospitalName}</div>
          </div>
        </div>

        <div className="flex flex-1 items-start justify-center px-5 py-8 sm:items-center sm:px-10 sm:py-10">
        <div className="w-full max-w-[420px]">
        <div className="mb-7">
          <span className="mb-5 hidden h-11 w-11 place-items-center rounded-xl bg-accent-soft text-accent ring-1 ring-accent-ring/60 lg:grid">
            <Icon name={mode === "signup" ? "shield" : "lock"} className="h-5 w-5" />
          </span>
          <h1 className="text-[24px] font-semibold tracking-tight text-ink">
            {mode === "signup" ? "Set up Dispensary Desk" : isCloud ? "Remote staff sign-in" : "Welcome back"}
          </h1>
          <p className="mt-1.5 text-[13.5px] text-muted">
            {mode === "signup" ? "First-time setup — create the administrator account."
              : isCloud ? "Sign in with your password and a one-time code sent to your mobile."
              : `Sign in to the ${hospitalName} dispensary.`}
          </p>
        </div>

        {mode === "loading" && <p className="py-6 text-center text-muted">Loading…</p>}
        {mode === "signup" && <SignUpForm onDone={onSignedUp} />}

        {mode === "signin" && (
          <>
            {info && <Notice>{info}</Notice>}
            {isCloud ? (
              <>
                {status && !status.live_operations && (
                  <Notice tone="warn">The hospital server is currently unreachable. After signing in you will have read-only access to
                    data synchronized {ago(status.last_sync)}.</Notice>
                )}
              </>
            ) : offline ? (
              <Notice tone="warn"><b>Internet unavailable — offline sign-in.</b> Previously verified accounts can sign in using
                credentials cached securely on the hospital server.</Notice>
            ) : null}
            {error && <Notice tone="error">{error}</Notice>}

            {!otp ? (
              <form onSubmit={submit} className="flex flex-col gap-3">
                <Field label="Username">
                  <input className="input" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
                </Field>
                <Field label="Password">
                  <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </Field>
                <button className="btn btn-primary btn-lg mt-2 w-full" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}<Icon name="arrowRight" /></button>
              </form>
            ) : (
              <form onSubmit={submitOtp} className="flex flex-col gap-3">
                <Notice>{otp.purpose === "verify" && <b>Verify your mobile number. </b>}A 6-digit code was sent to <b>{otp.masked_mobile}</b>.
                  It expires in {Math.round(otp.expires_in / 60)} minutes.</Notice>
                {otp.dev_code && <div className="rounded border border-dashed border-teal-300 bg-teal-50 p-2.5 text-xs">Development SMS: <b className="tracking-widest">{otp.dev_code}</b></div>}
                <Field label="One-time code">
                  <input className="input tracking-[0.4em]" inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus
                    value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
                </Field>
                <div className="mt-2 flex flex-wrap justify-end gap-2">
                  <button type="button" className="btn" onClick={() => { setOtp(null); setCode(""); }}>Back</button>
                  <button type="button" className="btn" onClick={resend}>Resend code</button>
                  <button className="btn btn-primary" disabled={busy || code.length !== 6}>Verify & sign in</button>
                </div>
              </form>
            )}
          </>
        )}
        </div>
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-4 text-[12px] text-muted sm:px-10">
          <span>© {new Date().getFullYear()} {hospitalName}</span>
          <span className="inline-flex items-center gap-1.5"><Icon name="lock" className="h-3.5 w-3.5" />Authorised hospital staff only</span>
        </footer>
      </main>
    </div>
  );
}

function SignUpForm({ onDone }: { onDone: (username: string) => void }) {
  const [f, setF] = useState({ hospital_name: "", low_stock_threshold: "50", full_name: "", username: "", mobile: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: k === "username" ? e.target.value.toLowerCase().replace(/\s/g, "") : e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (f.password.length < 6) return setError("Password must be at least 6 characters.");
    if (f.password !== f.confirm) return setError("The two passwords do not match.");
    setBusy(true);
    try {
      const { confirm: _confirm, ...body } = f;
      await api.post("/auth/setup", { ...body, low_stock_threshold: Number(f.low_stock_threshold) });
      onDone(f.username);
    } catch (err) {
      const apiErr = toApiError(err);
      if (apiErr.code === "ALREADY_SET_UP") onDone("");
      setError(apiErr.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Notice>No account exists yet. Fill in your dispensary details and create the <b>Admin</b> account. You will add billers
        later from <b>Users &amp; access</b>.</Notice>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="text-[11px] font-bold tracking-wider text-muted">DISPENSARY</div>
      <Field label="Hospital / dispensary name"><input className="input" required minLength={2} maxLength={120} autoFocus value={f.hospital_name} onChange={set("hospital_name")} /></Field>
      <Field label="Low-stock alert threshold (units)"><input className="input" type="number" min={0} required value={f.low_stock_threshold} onChange={set("low_stock_threshold")} /></Field>
      <div className="mt-1 text-[11px] font-bold tracking-wider text-muted">ADMIN ACCOUNT</div>
      <Field label="Full name"><input className="input" required minLength={2} maxLength={120} value={f.full_name} onChange={set("full_name")} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Username"><input className="input" required pattern="[a-z0-9._]{3,40}" title="3–40 characters: a–z, 0–9, dot or underscore" autoComplete="username" value={f.username} onChange={set("username")} /></Field>
        <Field label="Mobile number"><input className="input" required placeholder="+91 98xxx xxxxx" value={f.mobile} onChange={set("mobile")} /></Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Password (min 6 characters)"><input className="input" type="password" required autoComplete="new-password" value={f.password} onChange={set("password")} /></Field>
        <Field label="Confirm password"><input className="input" type="password" required autoComplete="new-password" value={f.confirm} onChange={set("confirm")} /></Field>
      </div>
      <button className="btn btn-primary btn-lg mt-2 w-full" disabled={busy}>{busy ? "Setting up…" : "Create Admin account"}</button>
    </form>
  );
}

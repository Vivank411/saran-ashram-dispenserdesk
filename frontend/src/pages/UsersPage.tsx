import { useState } from "react";
import type { Listing, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Avatar, Dot, Field, Modal, Notice, PageHeader, Panel, Table } from "../components/ui";
import { ago, fmtTime } from "../lib/format";
import { useAction, useGet, useStatus } from "../lib/hooks";

const MIN_PASSWORD = 6;

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function validateNewUser(f: { full_name: string; username: string; mobile: string; email: string; password: string }, mobileOptional: boolean): string {
  if (f.full_name.trim().length < 2) return "Enter the full name (at least 2 letters).";
  if (!/^[a-z0-9._]{3,40}$/.test(f.username)) return "Username: 3–40 lowercase letters, numbers, dot or underscore (no spaces).";
  if (!(mobileOptional && !f.mobile.trim()) && !/^\+?[0-9 ]{10,16}$/.test(f.mobile.trim())) return "Enter a valid mobile number (10 digits, e.g. 9876543210).";
  if (f.email.trim() && !EMAIL_RE.test(f.email.trim())) return "Enter a valid email address, e.g. name@gmail.com, or leave it empty.";
  if (f.password.length < MIN_PASSWORD) return `Password must be at least ${MIN_PASSWORD} characters.`;
  return "";
}

interface Meta { roles: string[]; permissions: Record<string, string>; matrix: Record<string, string[]> }

export default function UsersPage() {
  const { user: me } = useAuth();
  const { data: status } = useStatus();
  const toast = useToast();
  const { data } = useGet<Listing<User>>(["users"], "/users");
  const { data: meta } = useGet<Meta>(["roles"], "/meta/roles");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const directoryOk = status?.role === "cloud" || !!status?.cloud_reachable;
  const roles = meta?.roles ?? ["Admin", "Biller"];

  const create = useAction<object, User>("post", "/users", (u) => { toast(`${u.full_name} added`); setCreating(false); });
  const update = useAction<{ id: string } & object, User>("patch", (b) => `/users/${b.id}`, () => { toast("User updated"); setEditing(null); });
  const reset = useAction<{ id: string; password: string }, User>("post", (b) => `/users/${b.id}/reset-password`, () => { toast("Password reset — the user must sign in again"); setResetting(null); });
  const unlock = useAction<{ id: string }>("post", (b) => `/users/${b.id}/unlock`, () => toast("Account unlocked"));
  const revoke = useAction<{ id: string }>("post", (b) => `/users/${b.id}/revoke-sessions`, () => toast("All sessions signed out"));

  const [form, setForm] = useState({ full_name: "", username: "", mobile: "", email: "", role: "Biller", password: "" });
  const [edit, setEdit] = useState({ role: "", is_active: true, offline_login_enabled: true, email: "" });
  const [newPassword, setNewPassword] = useState("");
  const [formError, setFormError] = useState("");
  const submitCreate = () => {
    const err = validateNewUser(form, !!status?.standalone);
    setFormError(err);
    if (!err) create.mutate({ ...form, mobile: form.mobile.trim(), email: form.email.trim() });
  };
  const users = data?.items ?? [];

  return (
    <>
      <PageHeader title="Users & access" sub="Staff accounts and what each role can do. Every permission is enforced by the server."
        actions={<button className="btn btn-primary" disabled={!directoryOk} onClick={() => { setFormError(""); setCreating(true); }}><Icon name="plus" />Add user</button>} />
      {!directoryOk && <Notice tone="warn">The internet is unavailable, so accounts can't be added or changed right now. Existing staff can still sign in offline,
        and you can still unlock accounts or sign users out.</Notice>}

      <Panel title="Staff" sub={`${users.length} account${users.length === 1 ? "" : "s"}`} flush>
        <Table colSpan={6} head={<><th>User</th><th>Role</th><th>Mobile</th><th>Status</th><th>Last sign-in</th><th /></>}>
          {users.map((u) => {
            const locked = !!u.locked_until && new Date(u.locked_until) > new Date();
            return (
              <tr key={u.id}>
                <td>
                  <div className="flex items-center gap-3">
                    <Avatar name={u.full_name} />
                    <div><div className="font-semibold text-ink">{u.full_name}{u.id === me?.id && <span className="pill pill-blue ml-2">You</span>}</div>
                      <div className="text-xs text-muted">@{u.username}{u.email && <> · {u.email}</>}</div></div>
                  </div>
                </td>
                <td><span className={`pill ${u.role === "Admin" ? "pill-accent" : "pill-grey"}`}>{u.role === "Admin" && <Icon name="shield" className="h-3 w-3" />}{u.role}</span></td>
                <td className="tnum">{u.mobile_masked}</td>
                <td>
                  <div className="flex flex-wrap gap-1.5">
                    {!u.is_active ? <span className="pill pill-grey"><Dot tone="slate" />Deactivated</span>
                      : locked ? <span className="pill pill-bad"><Dot tone="bad" />Locked until {fmtTime(u.locked_until!)}</span>
                      : <span className="pill"><Dot tone="good" />Active</span>}
                    {!u.is_verified && <span className="pill pill-warn">Mobile not verified</span>}
                    {status?.email_otp && (u.email ? <span className="pill pill-blue">Email code on new devices</span>
                      : <span className="pill pill-grey" title="Add an email to turn on sign-in codes">Password only</span>)}
                    {u.offline_login_enabled && <span className="pill pill-grey">Offline sign-in</span>}
                  </div>
                </td>
                <td className="text-muted">{ago(u.last_login_at)}</td>
                <td>
                  <div className="flex justify-end gap-1.5">
                    <button className="btn btn-sm" disabled={!directoryOk} onClick={() => { setEditing(u); setEdit({ role: u.role, is_active: u.is_active, offline_login_enabled: u.offline_login_enabled, email: u.email ?? "" }); }}><Icon name="edit" className="h-3.5 w-3.5" />Edit</button>
                    <button className="btn btn-sm" disabled={!directoryOk} onClick={() => { setResetting(u); setNewPassword(""); }}><Icon name="key" className="h-3.5 w-3.5" />Password</button>
                    {locked && <button className="btn btn-sm" onClick={() => unlock.mutate({ id: u.id })}><Icon name="unlock" className="h-3.5 w-3.5" />Unlock</button>}
                    {u.id !== me?.id && <button className="btn btn-sm btn-danger" title="Sign this user out everywhere" onClick={() => confirm(`Sign ${u.full_name} out of all devices?`) && revoke.mutate({ id: u.id })}><Icon name="logout" className="h-3.5 w-3.5" /></button>}
                  </div>
                </td>
              </tr>
            );
          })}
        </Table>
      </Panel>

      {meta && (
        <Panel title="What each role can do" sub="Remote users get exactly the same permissions as at the hospital." flush>
          <Table head={<><th>Permission</th>{meta.roles.map((r) => <th key={r} className="text-center">{r}</th>)}</>}>
            {Object.entries(meta.permissions).map(([p, label]) => (
              <tr key={p}><td className="text-ink-soft">{label}</td>
                {meta.roles.map((r) => <td key={r} className="text-center">{meta.matrix[r].includes(p)
                  ? <Icon name="check" className="mx-auto h-4 w-4 text-good" strokeWidth={2.4} />
                  : <span className="text-slate-300">—</span>}</td>)}
              </tr>
            ))}
          </Table>
          <p className="border-t border-line px-5 py-3 text-xs text-muted">Billers can change stock and rates by sending a request; it is applied only after an Admin approves it.</p>
        </Panel>
      )}

      {creating && (
        <Modal title="Add a user" onClose={() => setCreating(false)} wide
          sub={status?.standalone ? "They can sign in right away with this username and password." : "They verify their mobile number with a one-time code on first sign-in. After that they can also sign in offline at the hospital."}
          footer={<><button className="btn" onClick={() => setCreating(false)}>Cancel</button><button className="btn btn-primary" disabled={create.isPending} onClick={submitCreate}>Add user</button></>}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name"><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Username" hint="Lowercase letters, numbers, dot or underscore"><input className="input" value={form.username} placeholder="e.g. priya.s" onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })} /></Field>
            <Field label={status?.standalone ? "Mobile number (optional)" : "Mobile number"}><input className="input" value={form.mobile} placeholder="+91 98xxx xxxxx" onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></Field>
            <Field label="Role">
              <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{roles.map((r) => <option key={r}>{r}</option>)}</select>
            </Field>
            <Field label={status?.email_otp ? "Email (for sign-in codes)" : "Email (optional)"} className="sm:col-span-2"
              hint={status?.email_otp ? "A code is emailed when they sign in on a new device. Leave empty to use the password only." : undefined}>
              <input className="input" type="email" value={form.email} placeholder="name@gmail.com" onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Password" hint={`At least ${MIN_PASSWORD} characters — letters, numbers or anything`} className="sm:col-span-2"><input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          </div>
          {formError && <div className="mt-4"><Notice tone="warn">{formError}</Notice></div>}
        </Modal>
      )}
      {editing && (
        <Modal title={`Edit ${editing.full_name}`} sub="Changing the role or deactivating the account signs the user out immediately." onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" disabled={update.isPending} onClick={() => { const email = edit.email.trim(); if (email && !EMAIL_RE.test(email)) { toast("Enter a valid email address, or leave it empty", "error"); return; } const body = { id: editing.id, ...edit, email }; update.mutate(body); }}>Save changes</button></>}>
          <div className="space-y-4">
            <Field label="Email" hint={status?.email_otp ? "Sign-in codes for new devices go here. Leave empty to use the password only." : undefined}>
              <input className="input" type="email" value={edit.email} placeholder="name@gmail.com" onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
            <Field label="Role"><select className="input" value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })}>{roles.map((r) => <option key={r}>{r}</option>)}</select></Field>
            <label className="flex items-center justify-between gap-4 rounded-lg border border-line px-4 py-3">
              <span><span className="block text-[13px] font-medium text-ink">Account active</span><span className="text-xs text-muted">Inactive users cannot sign in</span></span>
              <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between gap-4 rounded-lg border border-line px-4 py-3">
              <span><span className="block text-[13px] font-medium text-ink">Allow offline sign-in</span>
                <span className="text-xs text-muted">{editing.is_verified ? "Sign in at the hospital when the internet is down" : "Available after mobile verification"}</span></span>
              <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={edit.offline_login_enabled} disabled={!editing.is_verified}
                onChange={(e) => setEdit({ ...edit, offline_login_enabled: e.target.checked })} />
            </label>
          </div>
        </Modal>
      )}
      {resetting && (
        <Modal title={`Reset password · ${resetting.full_name}`} sub="The user is signed out everywhere and must use the new password." onClose={() => setResetting(null)}
          footer={<><button className="btn" onClick={() => setResetting(null)}>Cancel</button><button className="btn btn-primary" disabled={newPassword.length < MIN_PASSWORD || reset.isPending}
            onClick={() => reset.mutate({ id: resetting.id, password: newPassword })}>Reset password</button></>}>
          <Field label="New password" hint={`At least ${MIN_PASSWORD} characters`}><input className="input" type="password" autoFocus value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></Field>
        </Modal>
      )}
    </>
  );
}

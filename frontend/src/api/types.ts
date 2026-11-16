export type Source = "hospital" | "cloud_replica" | "hospital_live";

export interface User {
  id: string; username: string; full_name: string; mobile_masked: string; role: string; permissions: string[];
  is_active: boolean; is_verified: boolean; offline_login_enabled: boolean; locked_until: string | null;
  last_login_at: string | null; created_at: string;
}
export interface SessionInfo { id: string; channel: "lan" | "remote"; terminal: string; offline: boolean; expires_at: string }
export interface LoginOk { status: "ok"; access_token: string; user: User; session: SessionInfo }
export interface OtpRequired {
  status: "otp_required"; challenge_id: string; purpose: "login" | "verify"; masked_mobile: string; expires_in: number; dev_code?: string;
}
export interface Medicine {
  id: number; code: number; name: string; unit: string; stock: number; rate: string; cost: string; mrp: string; company: string;
  is_active: boolean; version: number; updated_at: string;
}
export interface BillItem { line_no: number; medicine_id: number; medicine_name: string; unit: string; qty: number; rate: string; amount: string }
export interface Bill {
  id: string; bill_no: string; request_id: string; status: "confirmed" | "reversed"; business_date: string; customer_name: string;
  patient_ref: string; payment_mode: string; total: string; operator_name: string; terminal: string; channel: string;
  created_offline: boolean; created_at: string; reversed_at: string | null; reversed_by: string | null;
  reversal_reason: string | null; reversal_ref: string | null; items: BillItem[];
}
export interface Movement {
  id: string; medicine_id: number; medicine_name: string; kind: string; qty_change: number; balance_after: number;
  reference: string; user_name: string; terminal: string; note: string | null; created_at: string;
}
export interface Adjustment {
  id: string; request_no: string; medicine_id: number; medicine_name: string; kind: "add" | "remove" | "set_count" | "set_rate";
  quantity: number | null; new_rate: string | null; reason: string; status: "pending" | "approved" | "rejected";
  requested_by_id: string; requested_by_name: string; requested_at: string; stock_at_request: number; rate_at_request: string;
  decided_by_name: string | null; decided_at: string | null; decision_note: string | null; channel: string;
}
export interface StockAlert {
  id: string; medicine_id: number; medicine_name: string; remaining: number; threshold: number; message: string;
  raised_at: string; updated_at: string; acknowledged_at: string | null; acknowledged_by: string | null;
}
export interface AuditEntry {
  id: string; at: string; username: string; user_name: string; action: string; detail: string; terminal: string;
  channel: string; offline: boolean; origin: string; synced: boolean;
}
export interface SystemStatus {
  role: "hospital" | "cloud"; hospital_name: string; server_time: string; low_stock_threshold: number; last_sync: string | null;
  timezone: string; hospital_reachable: boolean; live_operations: boolean; cloud_reachable: boolean; link_checked_at: string | null;
  pending: number | null; failed: number | null; conflicts: number;
}
export interface SyncEvent {
  seq: number; event_id: string; event_type: string; status: string; attempts: number | null; created_at: string;
  synced_at: string | null; next_attempt_at: string | null; last_error: string | null; resolution: { note: string; by: string } | null;
}
export interface SyncConflict {
  event_id: string; seq: number; event_type: string; detected_at: string; resolved_at: string | null; resolution_note: string | null;
  detail: { reason?: string; medicine_name?: string; cloud_stock?: number; cloud_version?: number; expected_version?: number;
    authoritative_stock?: number; authoritative_version?: number } | null;
}
export interface SyncDetail extends SystemStatus {
  last_error: string | null; last_attempt: string | null; synced_total: number; events: SyncEvent[]; conflict_list: SyncConflict[];
}
export interface ReportItem { medicine_id: number; medicine_name: string; unit: string; qty: number; amount: string; current_stock: number | null }
export interface Report {
  period: string; start: string; end: string; bills: number; reversed_bills: number; distinct_medicines: number; units: number;
  total: string; items: ReportItem[]; source: Source;
}
export interface Dashboard {
  date: string; sales: string; bills: number; units: number; low_stock: number; out_of_stock: number; medicines: number;
  threshold: number; active_alerts: number; alerts: StockAlert[]; top_medicines: ReportItem[]; recent_bills: Bill[]; source: Source;
}
export interface Listing<T> { items: T[]; source?: Source }

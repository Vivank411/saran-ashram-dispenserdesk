"""Database schema — identical on the hospital and cloud PostgreSQL instances.

Hospital: authoritative for medicines, bills, movements, adjustments, alerts; writes outbox_events.
Cloud:    authoritative for users/OTP; applies hospital events through inbox_events.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime
from .util import utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(12, 2)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    mobile: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    offline_login_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    directory_version: Mapped[int] = mapped_column(Integer, default=1)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_version: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(10))
    terminal: Mapped[str] = mapped_column(String(30))
    offline: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class TrustedDevice(Base):
    """A browser that completed email OTP; it skips the code until expires_at (stored as a SHA-256 of the cookie)."""
    __tablename__ = "trusted_devices"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (Index("ix_otp_user_created", "user_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(10))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Medicine(Base):
    __tablename__ = "medicines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # register code
    name: Mapped[str] = mapped_column(String(120), index=True)
    unit: Mapped[str] = mapped_column(String(20))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # selling rate
    cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), server_default="0")  # purchase cost
    mrp: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), server_default="0")
    company: Mapped[str] = mapped_column(String(60), default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bill_no: Mapped[str] = mapped_column(String(30), unique=True)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    status: Mapped[str] = mapped_column(String(12), index=True, default="confirmed")
    business_date: Mapped[date] = mapped_column(Date, index=True)
    customer_name: Mapped[str] = mapped_column(String(80), default="")
    patient_ref: Mapped[str] = mapped_column(String(40), default="")
    payment_mode: Mapped[str] = mapped_column(String(10))
    total: Mapped[Decimal] = mapped_column(Money)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    operator_name: Mapped[str] = mapped_column(String(120))
    terminal: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str] = mapped_column(String(10))
    created_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reversed_by: Mapped[str | None] = mapped_column(String(120))
    reversal_reason: Mapped[str | None] = mapped_column(String(200))
    reversal_ref: Mapped[str | None] = mapped_column(String(30))
    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="BillItem.line_no", lazy="selectin"
    )


class BillItem(Base):
    __tablename__ = "bill_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    medicine_id: Mapped[int] = mapped_column(Integer, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int] = mapped_column(Integer)
    rate: Mapped[Decimal] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)
    bill: Mapped[Bill] = relationship(back_populates="items")


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    medicine_id: Mapped[int] = mapped_column(Integer, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    qty_change: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(40))
    user_name: Mapped[str] = mapped_column(String(120))
    terminal: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AdjustmentRequest(Base):
    __tablename__ = "adjustment_requests"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_no: Mapped[str] = mapped_column(String(20), unique=True)
    medicine_id: Mapped[int] = mapped_column(Integer)
    medicine_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[int | None] = mapped_column(Integer)
    new_rate: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), index=True, default="pending")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    requested_by_name: Mapped[str] = mapped_column(String(120))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    stock_at_request: Mapped[int] = mapped_column(Integer)
    rate_at_request: Mapped[Decimal] = mapped_column(Money)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    decided_by_name: Mapped[str | None] = mapped_column(String(120))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_note: Mapped[str | None] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(10))


class StockAlert(Base):
    __tablename__ = "stock_alerts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    medicine_id: Mapped[int] = mapped_column(Integer, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120))
    remaining: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String(200))
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    username: Mapped[str] = mapped_column(String(40))
    user_name: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text)
    terminal: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str] = mapped_column(String(10))
    offline: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(10))
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(10), index=True, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSONType)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution: Mapped[dict | None] = mapped_column(JSONType)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    forced: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONType)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolution_note: Mapped[str | None] = mapped_column(String(300))


class SyncState(Base):
    __tablename__ = "sync_state"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(120))


class Counter(Base):
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)

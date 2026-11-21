import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .permissions import ROLES

RoleName = Literal[ROLES]  # type: ignore[valid-type]


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class OtpVerifyIn(_In):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class OtpResendIn(_In):
    challenge_id: uuid.UUID


class RefreshIn(_In):
    refresh_token: str | None = None


class BillItemIn(_In):
    medicine_id: int
    qty: int = Field(ge=1, le=100_000)


class BillCreate(_In):
    request_id: uuid.UUID  # client-generated idempotency key
    customer_name: str = Field("", max_length=80)
    patient_ref: str = Field("", max_length=40)
    payment_mode: Literal["Cash", "UPI", "Card", "Other"] = "Cash"
    items: list[BillItemIn] = Field(min_length=1, max_length=100)


class ReverseIn(_In):
    reason: str = Field(min_length=3, max_length=200)


class AdjustmentCreate(_In):
    medicine_id: int
    kind: Literal["add", "remove", "set_count", "set_rate"]
    quantity: int | None = Field(None, ge=0, le=10_000_000)
    new_rate: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=3, max_length=200)


class StockCsvImportIn(_In):
    csv_content: str
    mode: Literal["set_count", "add_stock"] = "set_count"
    reason: str = Field("CSV Bulk Stock Update", min_length=1, max_length=200)


class DecisionIn(_In):
    approve: bool
    note: str = Field("", max_length=200)


class ResolveIn(_In):
    note: str = Field(min_length=3, max_length=300)


class SettingsIn(_In):
    low_stock_threshold: int = Field(ge=0, le=1_000_000)
    hospital_name: str | None = Field(None, min_length=2, max_length=120)


class SetupAccount(_In):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(pattern=r"^[a-z0-9._]{3,40}$")
    mobile: str = Field(pattern=r"^\+?[0-9 ]{10,16}$")
    password: str = Field(min_length=1, max_length=200)


class SetupIn(SetupAccount):
    """First-time sign-up: creates the first Admin and the basic dispensary settings."""
    hospital_name: str = Field(min_length=2, max_length=120)
    low_stock_threshold: int = Field(50, ge=0, le=1_000_000)


class UserCreate(_In):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(pattern=r"^[a-z0-9._]{3,40}$")
    mobile: str = Field("", pattern=r"^(\+?[0-9 ]{10,16})?$")  # optional in standalone mode
    email: str = Field("", max_length=254, pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$")  # sign-in codes (standalone email OTP)
    role: RoleName
    password: str = Field(min_length=1, max_length=200)


class UserUpdate(_In):
    role: RoleName
    is_active: bool
    offline_login_enabled: bool
    email: str | None = Field(None, max_length=254, pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$")  # None = unchanged


class PasswordResetIn(_In):
    password: str = Field(min_length=1, max_length=200)

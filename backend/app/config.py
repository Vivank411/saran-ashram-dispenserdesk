from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE = {"", "change-me", "dev-secret", "dev-sync-secret"}


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    # hospital = local authoritative server, cloud = remote gateway + replica
    app_role: Literal["hospital", "cloud"] = "hospital"
    hospital_name: str = "Hospital Dispensary"
    timezone: str = "Asia/Kolkata"
    database_url: str = "sqlite:///./dispensary-dev.db"

    # authentication
    jwt_secret: str = "dev-secret"
    access_token_minutes: int = 15
    session_hours: int = 8
    cookie_secure: bool = False
    login_max_failures: int = 5
    lockout_minutes: int = 15
    login_rate_per_minute: int = 20

    # OTP / SMS (cloud side)
    otp_ttl_seconds: int = 300
    otp_max_sends: int = 3
    otp_window_minutes: int = 10
    otp_max_attempts: int = 3
    sms_provider: Literal["console", "webhook"] = "console"
    sms_webhook_url: str = ""
    sms_webhook_token: str = ""
    dev_expose_otp: bool = False

    # hospital <-> cloud link (over WireGuard)
    sync_shared_secret: str = "dev-sync-secret"
    peer_api_url: str = "http://localhost:8001"  # hospital: cloud API URL, cloud: hospital API URL
    peer_timeout_seconds: float = 5.0
    sync_interval_seconds: float = 5.0
    sync_batch_size: int = 100
    user_pull_interval_seconds: float = 30.0
    run_sync_worker: bool = False
    # standalone = one server only (e.g. Render + Neon): no cloud peer, nothing is queued for sync
    standalone: bool = False

    # Email OTP for standalone mode: a code is emailed the first time a user signs in on a new device,
    # then that device is trusted for trusted_device_days. Users without an email sign in with password only.
    email_otp: bool = False
    email_provider: Literal["console", "brevo", "smtp"] = "console"
    email_from: str = ""            # verified sender address, e.g. dispensary@gmail.com
    email_from_name: str = "Dispensary Desk"
    brevo_api_key: str = ""         # Brevo (free 300 emails/day) HTTP API key — works where SMTP ports are blocked
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = False          # True for port 465, False = STARTTLS (587)
    trusted_device_days: int = 30

    # inventory
    low_stock_threshold_default: int = 50

    cors_origins: str = ""

    @property
    def is_cloud(self) -> bool:
        return self.app_role == "cloud"

    @property
    def is_hospital(self) -> bool:
        return self.app_role == "hospital"

    @property
    def is_standalone(self) -> bool:
        return self.is_hospital and self.standalone

    @property
    def email_otp_enabled(self) -> bool:
        return self.is_standalone and self.email_otp

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            for name in ("jwt_secret", "sync_shared_secret"):
                value = getattr(self, name)
                if value in _INSECURE or len(value) < 32:
                    raise ValueError(f"{name.upper()} must be a random value of at least 32 characters in production")
            if self.dev_expose_otp:
                raise ValueError("DEV_EXPOSE_OTP must be false in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL (DATABASE_URL)")
            if self.email_otp_enabled:
                if self.email_provider == "console":
                    raise ValueError("EMAIL_PROVIDER must be brevo or smtp in production when EMAIL_OTP is on")
                if not self.email_from:
                    raise ValueError("EMAIL_FROM is required when EMAIL_OTP is on")
                if self.email_provider == "brevo" and not self.brevo_api_key:
                    raise ValueError("BREVO_API_KEY is required for EMAIL_PROVIDER=brevo")
                if self.email_provider == "smtp" and not (self.smtp_host and self.smtp_user and self.smtp_password):
                    raise ValueError("SMTP_HOST, SMTP_USER and SMTP_PASSWORD are required for EMAIL_PROVIDER=smtp")
            if self.is_cloud and not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true for the cloud deployment (HTTPS)")
        return self

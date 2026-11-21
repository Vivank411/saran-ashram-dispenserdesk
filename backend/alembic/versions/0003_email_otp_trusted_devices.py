"""user email and trusted devices (email OTP on new devices, standalone mode)

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("user_agent", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email")

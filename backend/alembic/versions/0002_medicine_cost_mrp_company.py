"""medicine cost, MRP and company (as in the original stock register)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("medicines") as batch:
        batch.add_column(sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("mrp", sa.Numeric(12, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("company", sa.String(length=60), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("medicines") as batch:
        batch.drop_column("company")
        batch.drop_column("mrp")
        batch.drop_column("cost")

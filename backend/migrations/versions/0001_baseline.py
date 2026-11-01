"""Schema do MVP anterior à proteção de publicação."""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issuer_cnpj", sa.String(14), nullable=False),
        sa.Column("number", sa.String(30), nullable=False),
        sa.Column("series", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issuer_cnpj", "number", "series", name="uq_invoice_identity"))
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_invoice_id", "audit_events", ["invoice_id"])
    op.create_table("documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id")),
        sa.Column("error", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_index("ix_executions_status", "executions", ["status"])

def downgrade():
    for table in ["executions", "documents", "audit_events", "invoices"]:
        op.drop_table(table)

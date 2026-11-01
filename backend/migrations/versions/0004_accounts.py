"""Contas por convite e separação do acervo legado."""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

def upgrade():
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(254), nullable=False, unique=True), sa.Column("password_hash", sa.String(256), nullable=False))
    op.create_table("invitations", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("email", sa.String(254), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_table("login_sessions", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("csrf_token", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_index("ix_login_sessions_expires_at", "login_sessions", ["expires_at"])
    sqlite = op.get_bind().dialect.name == "sqlite"
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    for table in ("invoices", "documents", "executions"):
        with op.batch_alter_table(table, naming_convention=convention) as batch:
            batch.add_column(sa.Column("owner_id", sa.String(36), nullable=False, server_default="legacy"))
            batch.create_index(f"ix_{table}_owner_id", ["owner_id"])
            if table == "invoices":
                batch.drop_constraint("uq_invoice_identity", type_="unique")
                batch.create_unique_constraint("uq_invoice_identity", ["owner_id", "issuer_cnpj", "number", "series"])
            else:
                batch.drop_constraint(f"uq_{table}_sha256" if sqlite else f"{table}_sha256_key", type_="unique")
                batch.create_unique_constraint(f"{table}_sha256_key", ["owner_id", "sha256"])

def downgrade():
    # O retorno à unicidade global perderia identidades válidas de usuários distintos.
    raise RuntimeError("Downgrade de contas exige reconciliação explícita dos dados; restaure backup validado.")

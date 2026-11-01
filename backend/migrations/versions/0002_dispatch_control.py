"""Reserva de publicação e orçamento de tentativas."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"

def upgrade():
    op.add_column("executions", sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE executions SET next_dispatch_at = CURRENT_TIMESTAMP")
    with op.batch_alter_table("executions") as batch:
        batch.alter_column("next_dispatch_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_index("ix_executions_next_dispatch_at", ["next_dispatch_at"])

def downgrade():
    with op.batch_alter_table("executions") as batch:
        batch.drop_index("ix_executions_next_dispatch_at")
        batch.drop_column("next_dispatch_at")
        batch.drop_column("dispatch_attempts")

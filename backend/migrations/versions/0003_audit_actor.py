"""Origem operacional dos eventos; não atribui identidade retroativa."""
import sqlalchemy as sa
from alembic import op
revision = "0003"
down_revision = "0002"

def upgrade():
    op.add_column("audit_events", sa.Column("actor", sa.String(80), nullable=False, server_default="legacy-unknown"))

def downgrade():
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_column("actor")

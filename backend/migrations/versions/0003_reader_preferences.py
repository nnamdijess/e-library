"""Owner reading preferences. Does not rewrite books or progress."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("reader_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("font_family", sa.String(20), nullable=False),
        sa.Column("font_size", sa.Integer(), nullable=False),
        sa.Column("line_height", sa.Float(), nullable=False),
        sa.Column("margin", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(10), nullable=False),
        sa.Column("pdf_zoom", sa.String(12), nullable=False))


def downgrade():
    op.drop_table("reader_preferences")

"""Owner/book progress with optimistic revisions. Existing data is untouched."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reading_progress",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("book_id", sa.String(36), sa.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("update_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision > 0", name="progress_revision"),
        sa.CheckConstraint("percentage >= 0 AND percentage <= 1", name="progress_percentage"),
    )


def downgrade():
    op.drop_table("reading_progress")

"""Initial owner, sessions, login throttle, and catalog. No progress table yet."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="single_owner"),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    throttle = op.create_table(
        "login_throttle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="single_throttle"),
    )
    op.bulk_insert(throttle, [{"id": 1, "window_start": 0, "attempts": 0}])
    op.create_table(
        "books",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(4), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("publisher", sa.String(500)),
        sa.Column("description", sa.Text()),
        sa.Column("language", sa.String(64)),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("cover_key", sa.String(255)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("format IN ('epub', 'pdf')", name="book_format"),
        sa.CheckConstraint("byte_size >= 0", name="book_size"),
        sa.CheckConstraint("page_count IS NULL OR page_count > 0", name="book_pages"),
        sa.CheckConstraint("artifact_version >= 1", name="book_artifact_version"),
        sa.UniqueConstraint("owner_id", "sha256", name="owner_book_hash"),
    )
    op.create_index("ix_books_owner_created", "books", ["owner_id", "created_at", "id"])


def downgrade():
    op.drop_table("books")
    op.drop_table("login_throttle")
    op.drop_table("sessions")
    op.drop_table("users")

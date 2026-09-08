"""Add knowledge-base visibility and explicit members."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing single knowledge base remains readable after migration.
    op.add_column(
        "knowledge_bases",
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
    )
    op.alter_column(
        "knowledge_bases",
        "visibility",
        existing_type=sa.String(20),
        existing_nullable=False,
        server_default="private",
    )
    op.add_column(
        "knowledge_bases", sa.Column("department", sa.String(50), nullable=True)
    )
    op.create_table(
        "knowledge_base_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_base_id", "user_id", name="uq_kb_member"),
    )
    op.create_index(
        "ix_knowledge_base_members_id", "knowledge_base_members", ["id"], unique=False
    )
    op.create_index(
        "ix_knowledge_base_members_knowledge_base_id",
        "knowledge_base_members",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_base_members_user_id",
        "knowledge_base_members",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("knowledge_base_members")
    op.drop_column("knowledge_bases", "department")
    op.drop_column("knowledge_bases", "visibility")

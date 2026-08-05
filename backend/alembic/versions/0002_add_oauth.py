"""add oauth sso support: nullable password_hash, avatar_url, user_oauth_links

Revision ID: 0002_add_oauth
Revises: 0001_initial
Create Date: 2026-08-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_oauth"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SSO-only accounts have no password — make password_hash nullable.
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)

    # Optional avatar URL synced from the OAuth provider.
    op.add_column("users", sa.Column("avatar_url", sa.String(length=500), nullable=True))

    # OAuth link table: which provider identity belongs to which user.
    op.create_table(
        "user_oauth_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )
    op.create_index("ix_user_oauth_links_user_id", "user_oauth_links", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_oauth_links_user_id", table_name="user_oauth_links")
    op.drop_table("user_oauth_links")
    op.drop_column("users", "avatar_url")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)

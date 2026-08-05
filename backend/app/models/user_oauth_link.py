"""OAuth provider link model (Google, Facebook, Microsoft)."""
import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserOAuthLink(Base):
    """A provider identity linked to a Book Quiz user.

    One user can link each provider at most once, and one provider identity
    can be linked to at most one user (both enforced by unique constraints).
    """

    __tablename__ = "user_oauth_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # One provider account can only be linked to one Book Quiz account.
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
        # One user can only link each provider once.
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    # Relationship (back-populated by User.oauth_links).
    user = relationship("User", back_populates="oauth_links")

    def __repr__(self) -> str:
        return f"<UserOAuthLink user={self.user_id} provider={self.provider}>"

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))

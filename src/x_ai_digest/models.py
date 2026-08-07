from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DigestPost:
    id: str
    url: str
    created_at: datetime
    username: str
    display_name: str
    text: str
    language: str
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    quotes: int = 0
    views: int = 0
    links: list[str] = field(default_factory=list)
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


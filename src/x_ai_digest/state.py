from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_seen(path: Path, keep_days: int = 30) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return set()

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    seen: set[str] = set()
    for post_id, timestamp in (data.get("posts") or {}).items():
        try:
            when = datetime.fromisoformat(str(timestamp))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff:
                seen.add(str(post_id))
        except ValueError:
            continue
    return seen


def update_seen(path: Path, existing: set[str], new_ids: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    data = {post_id: now for post_id in sorted(existing | set(new_ids))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"posts": data}, ensure_ascii=False, indent=2), encoding="utf-8")


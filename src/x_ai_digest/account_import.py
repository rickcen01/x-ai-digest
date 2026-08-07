from __future__ import annotations

import shutil
import sqlite3
import stat
from pathlib import Path


def import_account_db(source: Path, target: Path, proxy: str | None, force: bool = False) -> int:
    source = source.resolve()
    target = target.resolve()
    if not source.exists():
        raise FileNotFoundError(f"源账号库不存在：{source}")
    if source == target:
        raise ValueError("源账号库与目标账号库不能相同")
    if target.exists() and not force:
        raise FileExistsError(f"目标账号库已存在：{target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(stat.S_IREAD | stat.S_IWRITE)

    with sqlite3.connect(target) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
        updates = ["locks = '{}'", "last_used = NULL"]
        if "stats" in columns:
            updates.append("stats = '{}'")
        if "_tx" in columns:
            updates.append("_tx = NULL")
        if proxy is not None and "proxy" in columns:
            updates.append("proxy = ?")
            db.execute(f"UPDATE accounts SET {', '.join(updates)}", (proxy,))
        else:
            db.execute(f"UPDATE accounts SET {', '.join(updates)}")
        count = int(db.execute("SELECT COUNT(*) FROM accounts WHERE active = 1").fetchone()[0])
        db.commit()
    return count


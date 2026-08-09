from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from twscrape import AccountsPool
from twscrape.login import LoginConfig
from twscrape.logger import set_log_level

from .account_import import import_account_db
from .browser_client import fetch_home_timeline_browser, login_browser, login_browser_terminal
from .config import Settings, load_settings
from .delivery import deliver
from .digest import render_structured_digest, score_posts
from .llm import create_llm_digest
from .session_bundle import export_session, import_session
from .state import load_seen, update_seen
from .x_client import fetch_home_timeline


def _load(config_path: str) -> Settings:
    settings = load_settings(config_path)
    load_dotenv(settings.root / ".env")
    os.environ.setdefault("TWS_HTTP_BACKEND", "curl")
    return settings


def _write_report(settings: Settings, report: str, posts) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d")
    report_path = settings.reports_dir / f"{stamp}.md"
    report_path.write_text(report, encoding="utf-8")
    (settings.reports_dir / "latest.md").write_text(report, encoding="utf-8")
    json_path = settings.reports_dir / f"{stamp}.json"
    json_path.write_text(
        json.dumps([post.as_json() for post in posts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


async def _run(settings: Settings, preview: bool) -> dict:
    if settings.source == "browser":
        posts = await fetch_home_timeline_browser(settings)
    elif settings.source == "twscrape":
        posts = await fetch_home_timeline(settings)
    elif settings.source == "auto":
        try:
            posts = await fetch_home_timeline(settings)
        except Exception:
            posts = await fetch_home_timeline_browser(settings)
    else:
        raise ValueError("source 必须是 browser、twscrape 或 auto")
    seen_path = settings.state_dir / "seen.json"
    seen = set() if preview else load_seen(seen_path)
    candidates = [post for post in posts if post.id not in seen]
    ranked = score_posts(
        candidates,
        keywords=list(settings.digest.get("keywords") or []),
        lookback_hours=int(settings.digest.get("lookback_hours", 96)),
        minimum_keyword_score=float(settings.digest.get("minimum_keyword_score", 2.0)),
    )
    selected = ranked[: int(settings.digest.get("max_items", 10))]

    report = await create_llm_digest(selected, settings)
    if not report:
        report = render_structured_digest(
            selected,
            title=str(settings.digest.get("title", "X 每日 AI 情报")),
            fetched_count=len(posts),
        )
    report_path = _write_report(settings, report, selected)
    delivered = ["preview"] if preview else await deliver(report, settings)
    if not preview:
        update_seen(seen_path, seen, [post.id for post in selected])

    return {
        "ok": True,
        "fetched": len(posts),
        "matched": len(ranked),
        "selected": len(selected),
        "report": str(report_path),
        "delivered": delivered,
    }


async def _doctor(settings: Settings) -> dict:
    proxy_ok = None
    if settings.proxy:
        parsed = urlparse(settings.proxy)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        try:
            with socket.create_connection((host, port), timeout=3):
                proxy_ok = True
        except OSError:
            proxy_ok = False

    account_status = {"exists": settings.account_db.exists(), "total": 0, "active": 0}
    if settings.account_db.exists():
        pool = AccountsPool(str(settings.account_db), wait_timeout=0)
        stats = await pool.stats()
        account_status.update(total=int(stats.get("total", 0)), active=int(stats.get("active", 0)))

    browser_profile = Path(str(settings.browser["profile_dir"]))
    browser_ready = browser_profile.exists() and (settings.state_dir / "browser-auth.json").exists()
    source_ready = browser_ready if settings.source == "browser" else bool(account_status["active"])
    if settings.source == "auto":
        source_ready = source_ready or browser_ready

    return {
        "ok": source_ready and proxy_ok is not False,
        "account_db": str(settings.account_db),
        "accounts": account_status,
        "proxy": settings.proxy,
        "proxy_reachable": proxy_ok,
        "llm_configured": bool(
            settings.llm.get("enabled")
            and settings.llm.get("model")
            and os.getenv(str(settings.llm.get("api_key_env", "AI_DIGEST_LLM_API_KEY")))
        ),
        "delivery_channels": settings.delivery.get("channels", ["local"]),
        "source": settings.source,
        "browser_profile_ready": browser_ready,
    }


async def _refresh_account(settings: Settings, manual: bool) -> dict:
    if not settings.account_db.exists():
        raise FileNotFoundError(f"账号数据库不存在：{settings.account_db}")

    with sqlite3.connect(settings.account_db) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
        if "proxy" in columns:
            db.execute("UPDATE accounts SET proxy = ?", (settings.proxy,))
            db.commit()

    set_log_level("WARNING")
    pool = AccountsPool(
        str(settings.account_db),
        login_config=LoginConfig(email_first=False, manual=manual),
        wait_timeout=0,
    )
    account_info = await pool.accounts_info()
    usernames = [
        str(item["username"])
        for item in account_info
        if item.get("login_method") == "password"
    ]
    if not usernames:
        raise RuntimeError("账号库只有 Cookie 会话，没有可用于自动刷新的密码登录资料")

    await pool.relogin(usernames)
    stats = await pool.stats()
    active = int(stats.get("active", 0))
    return {
        "ok": active > 0,
        "attempted": len(usernames),
        "active": active,
        "inactive": int(stats.get("inactive", 0)),
        "manual": manual,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="X 每日 AI 情报")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="抓取并生成日报")
    run_parser.add_argument("--preview", action="store_true", help="不发送、不记录已读")

    sub.add_parser("doctor", help="检查账号、代理和发送配置")

    import_parser = sub.add_parser("import-account", help="复制已有 twscrape 账号库")
    import_parser.add_argument("--source", required=True, help="源 accounts.db")
    import_parser.add_argument("--force", action="store_true", help="覆盖目标数据库")

    refresh_parser = sub.add_parser("refresh-account", help="使用账号库资料刷新登录会话")
    refresh_parser.add_argument("--manual", action="store_true", help="在终端手动输入邮箱验证码")
    sub.add_parser("login-browser", help="打开独立浏览器并保存一次性登录会话")
    sub.add_parser("login-terminal", help="通过终端输入账号和挑战信息完成无头登录")

    export_parser = sub.add_parser("export-session", help="导出密码加密的可迁移会话包")
    export_parser.add_argument("--output", required=True, help="输出 .xsession 文件")

    import_session_parser = sub.add_parser("import-session", help="导入密码加密的会话包")
    import_session_parser.add_argument("--source", required=True, help="输入 .xsession 文件")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = _load(args.config)
    try:
        if args.command == "run":
            result = asyncio.run(_run(settings, preview=bool(args.preview)))
        elif args.command == "doctor":
            result = asyncio.run(_doctor(settings))
        elif args.command == "import-account":
            count = import_account_db(
                Path(args.source), settings.account_db, settings.proxy, force=bool(args.force)
            )
            result = {"ok": count > 0, "active_accounts_imported": count, "target": str(settings.account_db)}
        elif args.command == "refresh-account":
            result = asyncio.run(_refresh_account(settings, manual=bool(args.manual)))
        elif args.command == "login-browser":
            result = asyncio.run(login_browser(settings))
        elif args.command == "login-terminal":
            result = asyncio.run(login_browser_terminal(settings))
        elif args.command == "export-session":
            result = asyncio.run(export_session(settings, Path(args.output)))
        elif args.command == "import-session":
            result = asyncio.run(import_session(settings, Path(args.source)))
        else:
            raise ValueError(f"未知命令：{args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from exc

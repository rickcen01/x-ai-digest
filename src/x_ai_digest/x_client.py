from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from twscrape import AccountsPool
from twscrape.models import parse_tweets
from twscrape.xclid import XClIdGen, get_scripts_list

from .config import HOME_FEATURES, Settings
from .models import DigestPost


class TimelineError(RuntimeError):
    pass


class SessionExpiredError(TimelineError):
    pass


def _cookie_dict(cookie_jar) -> dict[str, str]:
    try:
        return {str(key): str(value) for key, value in cookie_jar.items()}
    except Exception:
        return {}


def _operation_url(operation: str) -> str:
    operation = operation.strip().lstrip("/")
    if not operation.endswith("/HomeTimeline"):
        operation = f"{operation.split('/')[0]}/HomeTimeline"
    return f"https://x.com/i/api/graphql/{operation}"


def _runtime_state_path(settings: Settings) -> Path:
    return settings.state_dir / "runtime.json"


def _load_runtime_operation(settings: Settings) -> str | None:
    path = _runtime_state_path(settings)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        operation = data.get("home_operation_id")
        return str(operation) if operation else None
    except (OSError, ValueError, TypeError):
        return None


def _save_runtime_operation(settings: Settings, operation: str) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    path = _runtime_state_path(settings)
    path.write_text(
        json.dumps(
            {"home_operation_id": operation, "updated_at": int(time.time())},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def _discover_home_operation(client) -> str:
    page = await client.get("https://x.com/home", timeout=30)
    page.raise_for_status()
    scripts = get_scripts_list(page.text)
    scripts.sort(key=lambda item: ("HomeTimeline" not in item, len(item)))

    patterns = [
        re.compile(r'queryId:"([^"]+)",operationName:"HomeTimeline"'),
        re.compile(r'operationName:"HomeTimeline",queryId:"([^"]+)"'),
    ]

    semaphore = asyncio.Semaphore(6)

    async def inspect_script(url: str) -> str | None:
        async with semaphore:
            try:
                response = await client.get(url, timeout=30)
                if response.status_code != 200:
                    return None
                for pattern in patterns:
                    match = pattern.search(response.text)
                    if match:
                        return f"{match.group(1)}/HomeTimeline"
            except Exception:
                return None
        return None

    for offset in range(0, len(scripts), 12):
        results = await asyncio.gather(*(inspect_script(url) for url in scripts[offset : offset + 12]))
        if operation := next((item for item in results if item), None):
            return operation

    raise TimelineError("无法从当前 X 网页脚本发现 HomeTimeline 操作 ID")


def _to_digest_post(tweet) -> DigestPost:
    links: list[str] = []
    for item in getattr(tweet, "links", []) or []:
        url = getattr(item, "url", None)
        if url and url not in links:
            links.append(url)
    card = getattr(tweet, "card", None)
    card_url = getattr(card, "url", None) if card else None
    if card_url and card_url not in links:
        links.append(card_url)

    user = tweet.user
    return DigestPost(
        id=str(tweet.id),
        url=str(tweet.url),
        created_at=tweet.date,
        username=str(user.username),
        display_name=str(user.displayname),
        text=str(tweet.rawContent or "").strip(),
        language=str(tweet.lang or ""),
        likes=int(tweet.likeCount or 0),
        reposts=int(tweet.retweetCount or 0),
        replies=int(tweet.replyCount or 0),
        quotes=int(tweet.quoteCount or 0),
        views=int(tweet.viewCount or 0),
        links=links,
    )


async def fetch_home_timeline(settings: Settings) -> list[DigestPost]:
    if not settings.account_db.exists():
        raise TimelineError(f"账号数据库不存在：{settings.account_db}")

    pool = AccountsPool(
        str(settings.account_db),
        raise_when_no_account=False,
        wait_timeout=0,
    )
    queue = "HomeTimeline"
    account = await pool.get_for_queue(queue)
    if account is None:
        raise TimelineError("没有可用的 active 账号，或 HomeTimeline 队列仍在冷却")

    proxy = account.resolve_proxy(settings.proxy)
    client = account.make_client(proxy=settings.proxy)
    released = False

    try:
        generator = await XClIdGen.create(proxy=proxy, cookies=account.cookies)
        operation = _load_runtime_operation(settings) or str(settings.home["operation_id"])
        count = max(1, min(int(settings.home.get("count", 20)), 40))
        payload = {
            "variables": {
                "count": count,
                "includePromotedContent": True,
                "requestContext": "launch",
                "withCommunity": True,
                "seenTweetIds": [],
            },
            "features": HOME_FEATURES,
            "queryId": operation.split("/", 1)[0],
        }

        async def request(current_operation: str):
            url = _operation_url(current_operation)
            path = urlparse(url).path or "/"
            headers = {
                "x-client-transaction-id": generator.calc("POST", path),
                "x-twitter-active-user": "yes",
                "x-twitter-auth-type": "OAuth2Session",
                "x-twitter-client-language": str(settings.home.get("language", "zh-cn")),
            }
            payload["queryId"] = current_operation.split("/", 1)[0]
            return await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=float(settings.home.get("timeout_seconds", 45)),
            )

        response = await request(operation)
        if response.status_code == 404 and settings.home.get("auto_discover_operation", True):
            operation = await _discover_home_operation(client)
            _save_runtime_operation(settings, operation)
            response = await request(operation)

        account.cookies.update(_cookie_dict(client.cookies))
        await pool.save(account)

        if response.status_code in {401, 403}:
            raise SessionExpiredError(f"X 会话被拒绝（HTTP {response.status_code}），需要重新导入登录会话")
        if response.status_code == 429:
            reset_at = int(response.headers.get("x-rate-limit-reset", time.time() + 900))
            await pool.lock_until(account.username, queue, reset_at, 1)
            released = True
            raise TimelineError("HomeTimeline 已触发速率限制，将在 X 指定时间后重试")
        if response.status_code != 200:
            body = response.text[:300].replace("\n", " ")
            raise TimelineError(f"HomeTimeline 请求失败：HTTP {response.status_code} {body}")

        await pool.unlock(account.username, queue, 1)
        released = True
        tweets = list(parse_tweets(response, limit=count))
        unique: dict[str, DigestPost] = {}
        for tweet in tweets:
            post = _to_digest_post(tweet)
            if post.id not in unique:
                unique[post.id] = post
        return list(unique.values())
    finally:
        await client.aclose()
        if not released:
            await pool.unlock(account.username, queue, 0)


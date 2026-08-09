from __future__ import annotations

import asyncio
import getpass
import json
import re
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright
from twscrape.models import parse_tweets

from .config import Settings
from .models import DigestPost


class BrowserSessionError(RuntimeError):
    pass


class _JsonResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _find_browser(configured: str) -> str:
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"配置的 Chromium 不存在：{path}")
        return str(path)

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    path = next((item for item in candidates if item.exists()), None)
    if path:
        return str(path)
    raise FileNotFoundError("未找到 Google Chrome 或 Microsoft Edge")


def _launch_options(settings: Settings, headless: bool) -> dict[str, Any]:
    options: dict[str, Any] = {
        "user_data_dir": str(Path(settings.browser["profile_dir"])),
        "headless": headless,
        "executable_path": _find_browser(str(settings.browser.get("executable_path") or "")),
        "locale": "zh-CN",
        "viewport": {"width": 1440, "height": 1000},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if settings.proxy:
        options["proxy"] = {"server": settings.proxy}
    return options


async def _logged_in(page: Page) -> bool:
    try:
        selectors = (
            '[data-testid="AppTabBar_Home_Link"]',
            'a[href="/home"]',
            'a[href="https://x.com/home"]',
        )
        for selector in selectors:
            if await page.locator(selector).count() > 0:
                return True
        return False
    except Exception:
        return False


async def _wait_for_logged_in(page: Page, timeout_seconds: float = 30) -> bool:
    deadline = asyncio.get_running_loop().time() + max(1, timeout_seconds)
    while asyncio.get_running_loop().time() < deadline:
        if await _logged_in(page):
            return True
        await asyncio.sleep(0.5)
    return False


def _to_digest_post(tweet) -> DigestPost:
    links: list[str] = []
    for item in getattr(tweet, "links", []) or []:
        url = getattr(item, "url", None)
        if url and url not in links:
            links.append(str(url))
    card = getattr(tweet, "card", None)
    card_url = getattr(card, "url", None) if card else None
    if card_url and card_url not in links:
        links.append(str(card_url))
    return DigestPost(
        id=str(tweet.id),
        url=str(tweet.url),
        created_at=tweet.date,
        username=str(tweet.user.username),
        display_name=str(tweet.user.displayname),
        text=str(tweet.rawContent or "").strip(),
        language=str(tweet.lang or ""),
        likes=int(tweet.likeCount or 0),
        reposts=int(tweet.retweetCount or 0),
        replies=int(tweet.replyCount or 0),
        quotes=int(tweet.quoteCount or 0),
        views=int(tweet.viewCount or 0),
        links=links,
    )


async def login_browser(settings: Settings) -> dict[str, Any]:
    profile_dir = Path(settings.browser["profile_dir"])
    profile_dir.mkdir(parents=True, exist_ok=True)
    timeout = max(1, int(settings.browser.get("login_timeout_minutes", 15))) * 60

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            **_launch_options(settings, headless=False)
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            for _ in range(timeout // 2):
                if await _wait_for_logged_in(page, timeout_seconds=1.5):
                    # Give Chromium a moment to flush the profile database before closing.
                    await page.wait_for_timeout(2000)
                    marker = settings.state_dir / "browser-auth.json"
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(
                        json.dumps({"logged_in": True, "profile_dir": str(profile_dir)}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return {"ok": True, "profile_dir": str(profile_dir)}
                await asyncio.sleep(2)
            raise BrowserSessionError("等待登录超时，请重新运行登录命令")
        finally:
            await context.close()


async def _click_flow_button(page: Page, labels: tuple[str, ...]) -> bool:
    selectors = (
        '[data-testid="ocfEnterTextNextButton"]',
        '[data-testid="LoginForm_Login_Button"]',
        '[data-testid="ocfEnterTextButton"]',
    )
    for selector in selectors:
        button = page.locator(selector)
        if await button.count() > 0:
            await button.first.click()
            return True
    for label in labels:
        pattern = re.compile(label, re.IGNORECASE)
        button = page.get_by_role("button", name=pattern)
        if await button.count() > 0:
            await button.first.click()
            return True
        button = page.locator('[role="button"]').filter(has_text=pattern)
        if await button.count() > 0:
            await button.first.click()
            return True
    return False


async def login_browser_terminal(settings: Settings) -> dict[str, Any]:
    """One-time terminal login for headless/phone-controlled cloud machines.

    The account password is entered by the user through getpass and is not
    written to project files. Only the resulting browser profile is retained.
    """
    profile_dir = Path(settings.browser["profile_dir"])
    profile_dir.mkdir(parents=True, exist_ok=True)
    username = input("X 用户名/邮箱/手机号（只在云电脑终端输入）: ").strip()
    password = getpass.getpass("X 密码（不会写入文件）: ")
    if not username or not password:
        raise ValueError("用户名和密码不能为空")

    timeout_seconds = max(60, int(settings.browser.get("login_timeout_minutes", 15)) * 60)
    username_submitted = False
    password_submitted = False
    challenge_attempts = 0

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            **_launch_options(settings, headless=True)
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=60000)
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            while asyncio.get_running_loop().time() < deadline:
                if await _logged_in(page):
                    marker = settings.state_dir / "browser-auth.json"
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(
                        json.dumps({"logged_in": True, "profile_dir": str(profile_dir)}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return {"ok": True, "profile_dir": str(profile_dir), "mode": "terminal"}

                if not username_submitted:
                    field = page.locator(
                        'input[autocomplete="username"]:visible, input[name="text"]:visible'
                    )
                    if await field.count() > 0:
                        await field.first.fill(username)
                        username_submitted = True
                        clicked = await _click_flow_button(page, (r"^Next$", r"^下一步$"))
                        if not clicked:
                            await field.first.press("Enter")
                        await page.wait_for_timeout(1000)
                        continue

                password_field = page.locator('input[type="password"]:visible')
                if not password_submitted and await password_field.count() > 0:
                    await password_field.first.fill(password)
                    password = ""
                    password_submitted = True
                    clicked = await _click_flow_button(page, (r"^Log in$", r"^登录$"))
                    if not clicked:
                        await password_field.first.press("Enter")
                    await page.wait_for_timeout(1500)
                    continue

                challenge_field = page.locator(
                    'input[autocomplete="one-time-code"]:visible, input[name="text"]:visible'
                )
                if password_submitted and await challenge_field.count() > 0:
                    if challenge_attempts >= 3:
                        raise BrowserSessionError("登录挑战次数过多，请改用远程桌面完成登录")
                    challenge = getpass.getpass(
                        "X 验证码或页面要求的额外信息（不会写入文件，直接回车取消）: "
                    ).strip()
                    if not challenge:
                        raise BrowserSessionError("未输入登录挑战信息")
                    await challenge_field.first.fill(challenge)
                    challenge_attempts += 1
                    clicked = await _click_flow_button(page, (r"^Next$", r"^下一步$", r"^Verify$", r"^验证$"))
                    if not clicked:
                        await challenge_field.first.press("Enter")
                    await page.wait_for_timeout(1500)
                    continue

                await asyncio.sleep(1)
            raise BrowserSessionError("无头登录超时，请检查代理或改用远程桌面登录")
        finally:
            await context.close()


async def _capture_home_response(page: Page, timeout_seconds: float) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    result: asyncio.Future[dict[str, Any]] = loop.create_future()

    async def inspect(response) -> None:
        if result.done() or "/HomeTimeline" not in response.url or response.status != 200:
            return
        try:
            payload = await response.json()
            if isinstance(payload, dict) and not result.done():
                result.set_result(payload)
        except Exception:
            return

    def on_response(response) -> None:
        asyncio.create_task(inspect(response))

    page.on("response", on_response)
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        if not await _wait_for_logged_in(page, timeout_seconds=30):
            raise BrowserSessionError("独立浏览器会话未登录，请先运行 scripts/login.ps1")
        try:
            return await asyncio.wait_for(result, timeout=timeout_seconds)
        except TimeoutError:
            await page.reload(wait_until="domcontentloaded", timeout=60000)
            return await asyncio.wait_for(result, timeout=timeout_seconds)
    finally:
        page.remove_listener("response", on_response)


async def fetch_home_timeline_browser(settings: Settings) -> list[DigestPost]:
    profile_dir = Path(settings.browser["profile_dir"])
    if not profile_dir.exists():
        raise BrowserSessionError("独立浏览器档案不存在，请先运行 scripts/login.ps1")

    async with async_playwright() as playwright:
        context: BrowserContext = await playwright.chromium.launch_persistent_context(
            **_launch_options(settings, headless=bool(settings.browser.get("headless", True)))
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            payload = await _capture_home_response(
                page, float(settings.browser.get("timeout_seconds", 60))
            )
            tweets = list(parse_tweets(_JsonResponse(payload), limit=int(settings.home.get("count", 20))))
            unique: dict[str, DigestPost] = {}
            for tweet in tweets:
                post = _to_digest_post(tweet)
                unique.setdefault(post.id, post)
            return list(unique.values())
        finally:
            await context.close()

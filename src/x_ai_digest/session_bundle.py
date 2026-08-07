from __future__ import annotations

import base64
import getpass
import json
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from playwright.async_api import async_playwright

from .browser_client import BrowserSessionError, _launch_options, _wait_for_logged_in
from .config import Settings


BUNDLE_FORMAT = "x-ai-digest-session-v1"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_state(state: dict[str, Any], passphrase: str) -> dict[str, str]:
    if len(passphrase) < 12:
        raise ValueError("会话包密码至少需要 12 个字符")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(passphrase, salt)
    plaintext = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, BUNDLE_FORMAT.encode("ascii"))
    return {
        "format": BUNDLE_FORMAT,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_state(bundle: dict[str, str], passphrase: str) -> dict[str, Any]:
    if bundle.get("format") != BUNDLE_FORMAT:
        raise ValueError("不支持的会话包格式")
    salt = base64.b64decode(bundle["salt"])
    nonce = base64.b64decode(bundle["nonce"])
    ciphertext = base64.b64decode(bundle["ciphertext"])
    key = _derive_key(passphrase, salt)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, BUNDLE_FORMAT.encode("ascii"))
    state = json.loads(plaintext.decode("utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise ValueError("会话包内容无效")
    return state


def _ask_passphrase(confirm: bool) -> str:
    passphrase = getpass.getpass("会话包加密密码（至少 12 个字符）: ")
    if confirm:
        repeated = getpass.getpass("再次输入密码: ")
        if passphrase != repeated:
            raise ValueError("两次输入的密码不一致")
    if len(passphrase) < 12:
        raise ValueError("会话包密码至少需要 12 个字符")
    return passphrase


async def export_session(settings: Settings, output: Path) -> dict[str, Any]:
    output = output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"目标会话包已存在：{output}")

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            # X can delay or suppress the authenticated shell in headless mode.
            # Export is an interactive, user-triggered operation, so use a visible
            # context for the one-time confirmation and keep scheduled runs headless.
            **_launch_options(settings, headless=False)
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            if not await _wait_for_logged_in(page, timeout_seconds=30):
                raise BrowserSessionError("独立浏览器档案未登录，无法生成会话包")
            await page.wait_for_timeout(2000)
            state = await context.storage_state()
        finally:
            await context.close()

    bundle = encrypt_state(state, _ask_passphrase(confirm=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    output.chmod(stat.S_IREAD | stat.S_IWRITE)
    return {"ok": True, "bundle": str(output), "encrypted": True}


async def import_session(settings: Settings, source: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"会话包不存在：{source}")
    bundle = json.loads(source.read_text(encoding="utf-8"))
    state = decrypt_state(bundle, _ask_passphrase(confirm=False))

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            **_launch_options(settings, headless=True)
        )
        try:
            await context.add_cookies(state["cookies"])
        finally:
            await context.close()

    marker = settings.state_dir / "browser-auth.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"imported": True, "profile_dir": settings.browser["profile_dir"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"ok": True, "profile_dir": str(settings.browser["profile_dir"]), "imported": True}

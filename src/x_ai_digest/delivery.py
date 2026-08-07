from __future__ import annotations

import os

import httpx

from .config import Settings


def _chunks(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


async def deliver(report: str, settings: Settings) -> list[str]:
    channels = {str(item).lower() for item in settings.delivery.get("channels", ["local"])}
    delivered = ["local"]

    async with httpx.AsyncClient(timeout=45) as client:
        if "feishu" in channels:
            env_name = str(settings.delivery.get("feishu_webhook_env", "AI_DIGEST_FEISHU_WEBHOOK"))
            webhook = os.getenv(env_name, "").strip()
            if not webhook:
                raise RuntimeError(f"已启用飞书发送，但环境变量 {env_name} 为空")
            for part in _chunks(report, 18000):
                response = await client.post(
                    webhook,
                    json={"msg_type": "text", "content": {"text": part}},
                )
                response.raise_for_status()
            delivered.append("feishu")

        if "telegram" in channels:
            token_env = str(
                settings.delivery.get("telegram_bot_token_env", "AI_DIGEST_TELEGRAM_BOT_TOKEN")
            )
            chat_env = str(
                settings.delivery.get("telegram_chat_id_env", "AI_DIGEST_TELEGRAM_CHAT_ID")
            )
            token = os.getenv(token_env, "").strip()
            chat_id = os.getenv(chat_env, "").strip()
            if not token or not chat_id:
                raise RuntimeError(f"已启用 Telegram，但 {token_env} 或 {chat_env} 为空")
            endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
            for part in _chunks(report, 3900):
                response = await client.post(
                    endpoint,
                    json={"chat_id": chat_id, "text": part, "disable_web_page_preview": False},
                )
                response.raise_for_status()
            delivered.append("telegram")

    return delivered


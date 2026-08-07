from __future__ import annotations

import json
import os

import httpx

from .config import Settings
from .models import DigestPost


async def create_llm_digest(posts: list[DigestPost], settings: Settings) -> str | None:
    config = settings.llm
    if not config.get("enabled") or not posts:
        return None

    model = str(config.get("model") or "").strip()
    key_env = str(config.get("api_key_env") or "AI_DIGEST_LLM_API_KEY")
    api_key = os.getenv(key_env, "").strip()
    if not model or not api_key:
        return None

    items = [
        {
            "id": post.id,
            "author": f"@{post.username}",
            "text": post.text,
            "url": post.url,
            "links": post.links,
            "likes": post.likes,
            "reposts": post.reposts,
        }
        for post in posts
    ]
    prompt = (
        "你是 AI 行业资讯编辑。根据下面来自用户 X 推荐流的帖子，生成简洁中文日报。"
        "只依据输入内容，不补充未经证实的事实；区分产品发布、研究、观点和传闻；"
        "每条都保留对应的原帖 URL，最后给出 3 条趋势判断。\n\n"
        + json.dumps(items, ensure_ascii=False)
    )
    base_url = str(config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    timeout = float(config.get("timeout_seconds", 90))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "输出 Markdown，语言为简体中文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    return str(content).strip() + "\n" if content else None


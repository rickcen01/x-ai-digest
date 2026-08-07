from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone

from .models import DigestPost


TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "模型发布": ("model", "模型", "release", "发布", "launch", "checkpoint", "weights"),
    "智能体": ("agent", "agentic", "智能体", "tool use", "mcp"),
    "开发工具": ("api", "sdk", "github", "开源", "open source", "framework", "code"),
    "多模态": ("multimodal", "多模态", "video", "image", "audio", "vision", "sora"),
    "研究进展": ("paper", "research", "benchmark", "论文", "研究", "reasoning"),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _topic_for(text: str) -> str:
    normalized = _normalize(text)
    scores = {
        topic: sum(1 for marker in markers if marker in normalized)
        for topic, markers in TOPIC_RULES.items()
    }
    topic, score = max(scores.items(), key=lambda item: item[1])
    return topic if score else "行业动态"


def score_posts(
    posts: list[DigestPost],
    keywords: list[str],
    lookback_hours: int,
    minimum_keyword_score: float,
    now: datetime | None = None,
) -> list[DigestPost]:
    now = now or datetime.now(timezone.utc)
    normalized_keywords = [item.strip().lower() for item in keywords if item.strip()]
    ranked: list[DigestPost] = []

    for post in posts:
        text = _normalize(post.text)
        matched = [keyword for keyword in normalized_keywords if keyword in text]
        keyword_score = sum(1.0 + min(len(keyword) / 18.0, 1.0) for keyword in matched)
        if keyword_score < minimum_keyword_score:
            continue

        created = post.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = max((now - created.astimezone(timezone.utc)).total_seconds() / 3600.0, 0.0)
        if age_hours > lookback_hours:
            continue

        engagement = post.likes + post.reposts * 2 + post.replies + post.quotes * 2
        recency = max(0.0, 3.0 - age_hours / max(lookback_hours, 1) * 3.0)
        post.score = round(keyword_score * 2.5 + math.log10(engagement + 1) + recency, 3)
        post.matched_keywords = matched
        ranked.append(post)

    ranked.sort(key=lambda item: (item.score, item.created_at), reverse=True)
    return ranked


def _short_summary(text: str, limit: int = 220) -> str:
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= limit:
        return clean
    boundary = max(clean.rfind("。", 0, limit), clean.rfind(". ", 0, limit))
    if boundary > 80:
        return clean[: boundary + 1]
    return clean[: limit - 1].rstrip() + "…"


def render_structured_digest(
    posts: list[DigestPost],
    title: str,
    fetched_count: int,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now().astimezone()
    lines = [
        f"# {title} — {generated_at:%Y-%m-%d}",
        "",
        f"> 由账号的 X“为你推荐”生成；本次读取 {fetched_count} 条，筛出 {len(posts)} 条 AI 资讯。",
        "",
    ]

    if not posts:
        lines.extend(
            [
                "今天的推荐流中没有发现满足时间与 AI 关键词条件的帖子。",
                "",
                "可以在 `config.json` 中增加关键词或扩大 `lookback_hours`。",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    topic_counts = Counter(_topic_for(post.text) for post in posts)
    overview = "、".join(f"{topic} {count} 条" for topic, count in topic_counts.most_common())
    lines.extend(["## 今日概览", "", overview, "", "## 推荐内容", ""])

    for index, post in enumerate(posts, 1):
        topic = _topic_for(post.text)
        author = f"{post.display_name} (@{post.username})"
        lines.extend(
            [
                f"### {index}. {topic} · {author}",
                "",
                _short_summary(post.text),
                "",
                f"互动：{post.likes:,} 赞 · {post.reposts:,} 转发 · {post.replies:,} 回复 · {post.views:,} 浏览",
                "",
                f"[查看原帖]({post.url})",
            ]
        )
        for link_index, link in enumerate(post.links[:3], 1):
            lines.append(f" · [相关链接 {link_index}]({link})")
        lines.append("")

    return "\n".join(lines).strip() + "\n"

